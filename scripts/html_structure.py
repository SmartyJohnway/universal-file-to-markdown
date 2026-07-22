"""Deterministic native HTML structure extraction (BeautifulSoup + lxml)."""
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag

def parse_html_source(path):
    with open(path, encoding="utf-8", errors="replace") as f: return BeautifulSoup(f.read(), "lxml")

def extract_main_content(soup):
    candidates = [("main_element", "main", "high", soup.find("main")), ("article_element", "article", "high", soup.find("article")),
        ("role_main", '[role="main"]', "high", soup.find(attrs={"role":"main"})), ("content_id", "#content", "medium", soup.find(id="content")),
        ("content_class", ".content", "medium", soup.find(class_="content")), ("body_fallback", "body", "low", soup.body)]
    for strategy, selector, confidence, node in candidates:
        if node: return node, {"strategy":strategy,"selector":selector,"confidence":confidence}, ([] if confidence != "low" else ["MAIN_CONTENT_NOT_IDENTIFIED", "BOILERPLATE_MAY_BE_INCLUDED"])
    return soup, {"strategy":"document_fallback","selector":"document","confidence":"low"}, ["MAIN_CONTENT_NOT_IDENTIFIED", "BOILERPLATE_MAY_BE_INCLUDED"]

def _url(value, base, warnings):
    if not value: return value
    if urlparse(value).scheme or value.startswith("//"): return value if not value.startswith("//") else "https:" + value
    if base: return urljoin(base, value)
    warnings.add("BASE_URL_UNAVAILABLE"); warnings.add("RELATIVE_URL_UNRESOLVED"); return value

def _text(node): return " ".join(node.stripped_strings)

def extract_cell_blocks(cell, base, warnings):
    blocks=[]
    for descendant in cell.find_all(["p","br","li","a","img"], recursive=True):
        if descendant.name == "br": blocks.append({"type":"line_break"})
        elif descendant.name == "li": blocks.append({"type":"list_item","level":len(descendant.find_parents(["ul","ol"])),"ordered":bool(descendant.find_parent("ol")),"text":_text(descendant)})
        elif descendant.name == "a": blocks.append({"type":"link","text":_text(descendant),"url":_url(descendant.get("href"),base,warnings)})
        elif descendant.name == "img": blocks.append({"type":"image","alt":descendant.get("alt", ""),"url":_url(descendant.get("src"),base,warnings),"remote_resource":True})
        elif descendant.name == "p": blocks.append({"type":"paragraph","text":_text(descendant)})
    return blocks or [{"type":"paragraph","text":_text(cell)}]

def _span(cell, key, warnings):
    raw=cell.get(key, "1")
    try:
        result=int(raw)
        if result < 1: raise ValueError
        return result
    except (TypeError, ValueError): warnings.add("HTML_TABLE_SPAN_INVALID"); return 1

def extract_table(table, index, base, warnings):
    rows=table.find_all("tr")
    grid=[]; cells=[]; merges=[]; cell_blocks=[]; occupied={}
    source_cells=0
    for r, tr in enumerate(rows):
        row=[]; c=0
        while (r,c) in occupied: row.append(occupied[(r,c)]); c+=1
        for cell in tr.find_all(["th","td"], recursive=False):
            source_cells+=1
            while (r,c) in occupied: row.append(occupied[(r,c)]); c+=1
            rs,cs=_span(cell,"rowspan",warnings),_span(cell,"colspan",warnings); value=_text(cell)
            blocks=extract_cell_blocks(cell,base,warnings)
            for rr in range(r,r+rs):
                for cc in range(c,c+cs):
                    if (rr,cc) in occupied: warnings.add("HTML_TABLE_SPAN_OVERLAP")
                    occupied[(rr,cc)]=value
            while len(row) < c: row.append(occupied.get((r,len(row)),""))
            row.extend([value]*cs); cells.append({"row":r,"column":c,"value":value,"rowspan":rs,"colspan":cs,"is_header":cell.name=="th"})
            if rs>1 or cs>1: merges.append({"anchor_row":r,"anchor_column":c,"rowspan":rs,"colspan":cs,"value":value})
            if len(blocks)>1 or blocks[0].get("type") != "paragraph": cell_blocks.append({"row":r,"column":c,"blocks":blocks})
            c+=cs
        grid.append(row)
    width=max((len(x) for x in grid),default=0)
    # Materialize rows created solely by rowspans and pad missing cells.
    for r in range(len(grid), max((rr for rr,_ in occupied), default=-1)+1): grid.append([])
    for r,row in enumerate(grid):
        row.extend(occupied.get((r,c),"") for c in range(len(row),width))
        if len(row)<width: row.extend([""]*(width-len(row)))
    locator={"format":"html","table_index":index}
    if table.get("id"): locator["element_id"]=table["id"]
    return {"id":f"table-html-{index:04d}","source_format":"html","source_locator":locator,"source_dimensions":{"row_count":len(rows),"source_cell_count":source_cells},"grid":grid,"cells":cells,"merged_cells":merges,"cell_blocks":cell_blocks,"engine":"beautifulsoup4_lxml"}

def render_table(grid):
    if not grid: return ""
    def esc(v): return str(v).replace("|", "\\|").replace("\n", "<br>")
    lines=["| " + " | ".join(esc(x) for x in grid[0]) + " |", "| " + " | ".join("---" for _ in grid[0]) + " |"]
    lines += ["| " + " | ".join(esc(x) for x in row) + " |" for row in grid[1:]]
    return "\n".join(lines)

def extract_html(path, source_url=None):
    soup=parse_html_source(path); base=source_url or (soup.base.get("href") if soup.base else None); main, main_info, warn_list=extract_main_content(soup); warnings=set(warn_list)
    for x in main.find_all(["script","style","noscript","template"]): x.decompose()
    tables=[]; elements=[]; heading_path=[]; table_number=0; element_index=0
    for node in main.find_all(["h1","h2","h3","h4","h5","h6","p","ul","ol","table","img"], recursive=True):
        if node.find_parent("table") and node.name != "table": continue
        if node.find_parent(["ul","ol"]) and node.name in ("ul","ol"): continue
        element_index+=1; locator={"format":"html","element_index":element_index}
        if node.get("id"): locator["element_id"]=node["id"]
        if node.name.startswith("h"):
            level=int(node.name[1]); text=_text(node); heading_path=heading_path[:level-1]+[text]
            elements.append({"id":f"html-heading-{element_index:04d}","type":"heading","content":"#"*level+" "+text,"heading_path":heading_path[:-1],"source_locator":locator,"locator_precision":"exact","properties":{"level":level}})
        elif node.name == "table":
            table_number+=1; t=extract_table(node,table_number,base,warnings); tables.append(t); elements.append({"id":f"html-table-{table_number:04d}","type":"table","content":render_table(t["grid"]),"table_id":t["id"],"heading_path":heading_path,"source_locator":locator,"locator_precision":"exact"})
        elif node.name == "img": elements.append({"id":f"html-image-{element_index:04d}","type":"image","content":f"![{node.get('alt','')}]({_url(node.get('src'),base,warnings)})","heading_path":heading_path,"source_locator":locator,"locator_precision":"exact","properties":{"remote_resource":True}})
        else:
            text=_text(node)
            if text: elements.append({"id":f"html-{node.name}-{element_index:04d}","type":"list" if node.name in ("ul","ol") else "paragraph","content":text,"heading_path":heading_path,"source_locator":locator,"locator_precision":"exact"})
    source={"heading_count":len(main.find_all(["h1","h2","h3","h4","h5","h6"])),"table_count":len(tables),"table_row_count":sum(t['source_dimensions']['row_count'] for t in tables),"source_cell_count":sum(t['source_dimensions']['source_cell_count'] for t in tables),"rowspan_anchor_count":sum(sum(x['rowspan']>1 for x in t['merged_cells']) for t in tables),"colspan_anchor_count":sum(sum(x['colspan']>1 for x in t['merged_cells']) for t in tables),"merged_cell_anchor_count":sum(len(t['merged_cells']) for t in tables),"link_count":len(main.find_all('a')),"relative_link_count":sum(not urlparse(a.get('href','')).scheme and not a.get('href','').startswith('//') for a in main.find_all('a')),"image_count":len(main.find_all('img'))}
    canonical={"heading_count":sum(e['type']=='heading' for e in elements),"table_count":len(tables),"table_row_count":sum(len(t['grid']) for t in tables),"expanded_grid_cell_count":sum(sum(len(r) for r in t['grid']) for t in tables),"merged_cell_anchor_count":sum(len(t['merged_cells']) for t in tables),"resolved_link_count":source['link_count'] if base else source['link_count']-source['relative_link_count'],"unresolved_relative_link_count":source['relative_link_count'] if not base else 0,"image_reference_count":sum(e['type']=='image' for e in elements)}
    return {"markdown":"\n\n".join(e['content'] for e in elements),"elements":elements,"tables":tables,"report":{"status":"passed","engine":"beautifulsoup4_lxml","source_url":source_url,"main_content":main_info,"html_structure":{"source_metrics":source,"canonical_metrics":canonical},"warnings":[{"code":x,"message":x} for x in sorted(warnings)]}}
