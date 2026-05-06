"""Safe local file-generation helper for the desktop pet."""

import os
import re
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape

DEFAULT_AGENT_FILE_NAME_MAX_CHARS = 48

@dataclass
class FileAgentAction:
    kind: str
    name: str
    title: str = ""
    content: str = ""

FILE_AGENT_CONFIRM_WORDS = ("确认", "确认创建", "确认执行", "可以", "执行", "好", "没问题")

FILE_AGENT_CANCEL_WORDS = ("取消", "算了", "不要", "停止", "别创建", "先别")

FILE_AGENT_FOLDER_KEYWORDS = ("创建文件夹", "新建文件夹", "建文件夹", "建个文件夹", "新建目录", "创建目录")

FILE_AGENT_DOCX_KEYWORDS = ("写word", "写Word", "新建word", "创建word", "生成word", "写文档", "新建文档", "创建文档", "docx")

FILE_AGENT_PPTX_KEYWORDS = ("写ppt", "写PPT", "新建ppt", "创建ppt", "生成ppt", "做ppt", "做PPT", "pptx")

def file_agent_clean_name(name, default_name, max_chars=DEFAULT_AGENT_FILE_NAME_MAX_CHARS):
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip(" ._")
    if not name:
        name = default_name
    return name[:max_chars].strip(" ._") or default_name

def file_agent_unique_path(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    for index in range(2, 1000):
        candidate = f"{root}_{index}{ext}"
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError("同名文件太多，无法继续创建。")

def file_agent_safe_path(name, extension="", base_dir=None, max_chars=DEFAULT_AGENT_FILE_NAME_MAX_CHARS):
    if not base_dir:
        raise RuntimeError("缺少文件代理安全目录。")
    os.makedirs(base_dir, exist_ok=True)
    clean_name = file_agent_clean_name(name, "桌宠文件", max_chars=max_chars)
    if extension and not clean_name.lower().endswith(extension.lower()):
        clean_name = f"{clean_name}{extension}"
    root = os.path.abspath(base_dir)
    path = os.path.abspath(os.path.join(root, clean_name))
    if os.path.commonpath([root, path]) != root:
        raise RuntimeError("文件路径超出安全目录，已拒绝。")
    return file_agent_unique_path(path)

def file_agent_extract_after(text, keywords):
    for keyword in keywords:
        index = text.find(keyword)
        if index == -1:
            continue
        value = text[index + len(keyword):].strip(" ：:，,。.!！?？")
        if value:
            return value
    return ""

def file_agent_extract_title(text, default_title):
    for pattern in (
        r"(?:标题|题目|文件名|名字|名称)(?:是|叫|为|：|:)\s*(.{1,60}?)(?=\s*(?:内容|正文|文字|大纲)(?:是|为|：|:)|[，。；;！!？?\n]|$)",
        r"(?:关于|主题是|主题为)\s*(.{1,60}?)(?=\s*(?:内容|正文|文字|大纲)(?:是|为|：|:)|[，。；;！!？?\n]|$)",
    ):
        match = re.search(pattern, text)
        if match:
            return file_agent_clean_name(match.group(1), default_title)
    return default_title

def file_agent_extract_content(text, title):
    for pattern in (
        r"(?:内容|正文|文字|大纲)(?:是|为|：|:)\s*(.+)",
        r"(?:写成|写下|记录)\s*(.+)",
    ):
        match = re.search(pattern, text, flags=re.S)
        if match:
            return match.group(1).strip()
    cleaned = text
    for keyword in (*FILE_AGENT_DOCX_KEYWORDS, *FILE_AGENT_PPTX_KEYWORDS):
        cleaned = cleaned.replace(keyword, "")
    cleaned = re.sub(r"(?:标题|题目|文件名|名字|名称)(?:是|叫|为|：|:)\s*[^，。；;！!？?\n]{1,60}", "", cleaned)
    cleaned = re.sub(r"(?:关于|主题是|主题为)\s*[^，。；;！!？?\n]{1,60}", "", cleaned)
    cleaned = cleaned.strip(" ：:，,。.!！?？")
    return cleaned or f"{title}\n\n待补充。"

def parse_file_agent_action(text):
    text = (text or "").strip()
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None

    if any(keyword in compact for keyword in FILE_AGENT_FOLDER_KEYWORDS):
        name = file_agent_extract_after(text, FILE_AGENT_FOLDER_KEYWORDS)
        name = re.sub(r"^(叫|名为|名字是|名称是)", "", name).strip(" ：:，,。")
        return FileAgentAction("folder", file_agent_clean_name(name, "新建文件夹"))

    if any(keyword.lower() in compact.lower() for keyword in FILE_AGENT_DOCX_KEYWORDS):
        title = file_agent_extract_title(text, "桌宠文档")
        content = file_agent_extract_content(text, title)
        return FileAgentAction("docx", title, title=title, content=content)

    if any(keyword.lower() in compact.lower() for keyword in FILE_AGENT_PPTX_KEYWORDS):
        title = file_agent_extract_title(text, "桌宠演示")
        content = file_agent_extract_content(text, title)
        return FileAgentAction("pptx", title, title=title, content=content)

    return None

def file_agent_is_confirm(text):
    compact = re.sub(r"\s+", "", text or "")
    return compact in FILE_AGENT_CONFIRM_WORDS or compact.startswith("确认")

def file_agent_is_cancel(text):
    compact = re.sub(r"\s+", "", text or "")
    return any(word in compact for word in FILE_AGENT_CANCEL_WORDS)

def describe_file_agent_action(action):
    if action.kind == "folder":
        return f"创建文件夹：{action.name}"
    if action.kind == "docx":
        return f"创建 Word：{action.name}.docx"
    if action.kind == "pptx":
        return f"创建 PPT：{action.name}.pptx"
    return "未知文件操作"

def split_agent_paragraphs(content):
    lines = [line.strip() for line in re.split(r"[\r\n]+", content or "") if line.strip()]
    if lines:
        return lines[:24]
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?；;])", content or "") if part.strip()]
    return parts[:24] or ["待补充。"]

def write_docx_file(path, title, content):
    paragraphs = [title, *split_agent_paragraphs(content)]
    body = []
    for index, paragraph in enumerate(paragraphs):
        style = '<w:pStyle w:val="Title"/>' if index == 0 else ""
        body.append(
            "<w:p>"
            f"<w:pPr>{style}</w:pPr>"
            f'<w:r><w:t xml:space="preserve">{escape(paragraph)}</w:t></w:r>'
            "</w:p>"
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        docx.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>",
        )
        docx.writestr("word/document.xml", document_xml)

def pptx_slide_text_xml(text):
    paragraphs = split_agent_paragraphs(text)
    return "".join(f'<a:p><a:r><a:t>{escape(paragraph)}</a:t></a:r></a:p>' for paragraph in paragraphs)

def pptx_slide_xml(title, body):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="685800" y="457200"/><a:ext cx="7772400" cy="914400"/></a:xfrm></p:spPr>'
        f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="zh-CN" sz="3600" b="1"/><a:t>{escape(title)}</a:t></a:r></a:p></p:txBody></p:sp>'
        '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="914400" y="1828800"/><a:ext cx="7315200" cy="4114800"/></a:xfrm></p:spPr>'
        f'<p:txBody><a:bodyPr/><a:lstStyle/>{pptx_slide_text_xml(body)}</p:txBody></p:sp>'
        '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )

def write_pptx_file(path, title, content):
    raw_slides = [part.strip() for part in re.split(r"(?:\n\s*\n|第[一二三四五六七八九十0-9]+页[:：]?)", content or "") if part.strip()]
    if not raw_slides:
        raw_slides = split_agent_paragraphs(content)
    slides = raw_slides[:8] or ["待补充。"]
    overrides = "".join(
        f'<Override PartName="/ppt/slides/slide{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for index in range(1, len(slides) + 1)
    )
    sld_ids = "".join(f'<p:sldId id="{255 + index}" r:id="rId{index + 1}"/>' for index in range(1, len(slides) + 1))
    rels = '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    rels += "".join(
        f'<Relationship Id="rId{index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>'
        for index in range(1, len(slides) + 1)
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            f"{overrides}</Types>",
        )
        pptx.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            "</Relationships>",
        )
        pptx.writestr(
            "ppt/presentation.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            f"<p:sldIdLst>{sld_ids}</p:sldIdLst>"
            '<p:sldSz cx="9144000" cy="6858000" type="screen4x3"/><p:notesSz cx="6858000" cy="9144000"/>'
            "</p:presentation>",
        )
        pptx.writestr("ppt/_rels/presentation.xml.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        pptx.writestr("ppt/slideMasters/slideMaster1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>')
        pptx.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>')
        pptx.writestr("ppt/slideLayouts/slideLayout1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="titleAndObj" preserve="1"><p:cSld name="Title and Content"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld></p:sldLayout>')
        pptx.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>')
        pptx.writestr("ppt/theme/theme1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="PersonaPet"><a:themeElements><a:clrScheme name="PersonaPet"><a:dk1><a:srgbClr val="222222"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2><a:accent1><a:srgbClr val="C45A8A"/></a:accent1><a:accent2><a:srgbClr val="5B9BD5"/></a:accent2><a:accent3><a:srgbClr val="70AD47"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4><a:accent5><a:srgbClr val="4472C4"/></a:accent5><a:accent6><a:srgbClr val="ED7D31"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme><a:fontScheme name="PersonaPet"><a:majorFont><a:latin typeface="Microsoft YaHei"/></a:majorFont><a:minorFont><a:latin typeface="Microsoft YaHei"/></a:minorFont></a:fontScheme><a:fmtScheme name="PersonaPet"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme></a:themeElements></a:theme>')
        for index, slide in enumerate(slides, 1):
            pptx.writestr(f"ppt/slides/slide{index}.xml", pptx_slide_xml(title if index == 1 else f"{title} {index}", slide))
            pptx.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>')

def execute_file_agent_action(action, base_dir, logger=None, max_chars=DEFAULT_AGENT_FILE_NAME_MAX_CHARS):
    if action.kind == "folder":
        path = file_agent_safe_path(action.name, base_dir=base_dir, max_chars=max_chars)
        os.makedirs(path, exist_ok=False)
    elif action.kind == "docx":
        path = file_agent_safe_path(action.name, ".docx", base_dir=base_dir, max_chars=max_chars)
        write_docx_file(path, action.title or action.name, action.content)
    elif action.kind == "pptx":
        path = file_agent_safe_path(action.name, ".pptx", base_dir=base_dir, max_chars=max_chars)
        write_pptx_file(path, action.title or action.name, action.content)
    else:
        raise RuntimeError("未知文件操作。")
    if logger:
        logger("FILE_AGENT_EXECUTE", {"kind": action.kind, "path": path})
    return path
