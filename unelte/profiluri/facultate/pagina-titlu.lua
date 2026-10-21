-- Filtru pandoc: pagina de titlu din antetul YAML, urmată de un salt de pagină.
-- Câmpuri: universitate, facultate, specializare, titlu (sau title), subtitlu, tip_lucrare,
-- autor (sau author), coordonator, oras, an.
-- Paragrafele folosesc stilurile „Pagina titlu” și „Titlu lucrare” din reference.docx.

local PAGE_BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
local TOC = '<w:sdt><w:sdtPr><w:docPartObj><w:docPartGallery w:val="Table of Contents"/><w:docPartUnique/>'
  .. '</w:docPartObj></w:sdtPr><w:sdtContent>'
  .. '<w:p><w:pPr><w:pStyle w:val="TOCHeading"/></w:pPr><w:r><w:t xml:space="preserve">Cuprins</w:t></w:r></w:p>'
  .. '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/>'
  .. '<w:instrText xml:space="preserve">TOC \\o "1-3" \\h \\z \\u</w:instrText>'
  .. '<w:fldChar w:fldCharType="separate"/><w:fldChar w:fldCharType="end"/></w:r></w:p>'
  .. '</w:sdtContent></w:sdt>'

local function text(v)
  if v == nil then return nil end
  local s = pandoc.utils.stringify(v)
  if s == "" then return nil end
  return s
end

local function para(style, s)
  return pandoc.Div({ pandoc.Para({ pandoc.Str(s) }) }, pandoc.Attr("", {}, { ["custom-style"] = style }))
end

local function spacer(n)
  local out = {}
  for _ = 1, n do
    table.insert(out, para("Pagina titlu", "\u{00A0}"))
  end
  return out
end

function Pandoc(doc)
  local m = doc.meta
  local titlu = text(m.titlu) or text(m.title)
  if not titlu then return doc end
  local blocks = {}
  local function add(style, value)
    if value then table.insert(blocks, para(style, value)) end
  end
  add("Pagina titlu", text(m.universitate))
  add("Pagina titlu", text(m.facultate))
  add("Pagina titlu", text(m.specializare))
  for _, b in ipairs(spacer(6)) do table.insert(blocks, b) end
  add("Pagina titlu", text(m.tip_lucrare))
  add("Titlu lucrare", titlu)
  add("Pagina titlu", text(m.subtitlu) or text(m.subtitle))
  for _, b in ipairs(spacer(6)) do table.insert(blocks, b) end
  local coord = text(m.coordonator)
  if coord then add("Pagina titlu", "Coordonator științific: " .. coord) end
  local autor = text(m.autor) or text(m.author)
  if autor then add("Pagina titlu", "Autor: " .. autor) end
  for _, b in ipairs(spacer(4)) do table.insert(blocks, b) end
  local loc = { text(m.oras), text(m.an) or text(m.date) }
  local parts = {}
  for _, v in ipairs(loc) do if v then table.insert(parts, v) end end
  if #parts > 0 then add("Pagina titlu", table.concat(parts, ", ")) end
  table.insert(blocks, pandoc.RawBlock("openxml", PAGE_BREAK))
  -- cu pagină de titlu, cuprinsul se pune aici (după ea), nu înaintea ei ca la --toc
  if m.cuprins == true or text(m.cuprins) == "true" then
    table.insert(blocks, pandoc.RawBlock("openxml", TOC))
    table.insert(blocks, pandoc.RawBlock("openxml", PAGE_BREAK))
  end
  -- titlul implicit al pandoc nu se mai afișează (pagina de titlu îl înlocuiește)
  doc.meta.title = nil
  doc.meta.subtitle = nil
  doc.meta.author = nil
  doc.meta.date = nil
  for i = #blocks, 1, -1 do
    table.insert(doc.blocks, 1, blocks[i])
  end
  return doc
end
