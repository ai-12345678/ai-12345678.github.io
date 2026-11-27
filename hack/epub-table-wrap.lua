local function wrap_cell_code(code)
  local text = code.text
  if #text < 18 or text:find("%s") then
    return
  end
  if code.identifier ~= "" or #code.classes > 0 or #code.attributes > 0 then
    return
  end

  -- Soft breaks at separators and case changes keep technical values copyable.
  local escaped = text:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;")
  local wrapped = escaped:gsub("([_/:]+)", "%1<wbr />")
  wrapped = wrapped:gsub("([a-z0-9])([A-Z])", "%1<wbr />%2")
  if wrapped == escaped then
    return
  end
  return pandoc.RawInline("html", "<code>" .. wrapped .. "</code>")
end

function Table(tbl)
  local wrapped = tbl:walk({ Code = wrap_cell_code })
  return pandoc.Div({ wrapped }, pandoc.Attr("", { "book-table" }))
end
