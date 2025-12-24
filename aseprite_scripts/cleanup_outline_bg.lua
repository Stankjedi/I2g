--[[
    cleanup_outline_bg.lua
    Enhanced flood-fill based background removal for AI-generated images.
    
    ALGORITHM (v4):
    1. Flood-fill from image edges (stops at dark outline)
    2. Aggressive edge dilation: remove ANY non-outline pixel adjacent to removed area
    3. Multiple dilation passes to catch all edge remnants
    
    This preserves internal content while removing ALL edge remnants.
]]

-- Parse parameters
local function getParam(name, default)
    local val = app.params[name]
    if val == nil or val == "" then return default end
    return val
end

local function getParamNumber(name, default)
    local val = app.params[name]
    if val == nil or val == "" then return default end
    return tonumber(val) or default
end

local function getParamBool(name, default)
    local val = app.params[name]
    if val == nil or val == "" then return default end
    return val == "true" or val == "1"
end

-- Parameters
local inputPath = getParam("input_path", "")
local outputPath = getParam("output_path", "")
local outlineThreshold = getParamNumber("outline_threshold", 50)
local fillTolerance = getParamNumber("fill_tolerance", 80)
local dilationPasses = getParamNumber("dilation_passes", 20)
local previewMode = getParamBool("preview_mode", false)

-- Simple JSON serialization
local function serializeJson(obj, indent)
    indent = indent or 0
    local spaces = string.rep("  ", indent)
    local t = type(obj)
    if t == "nil" then return "null"
    elseif t == "boolean" then return tostring(obj)
    elseif t == "number" then
        if obj ~= obj then return "null" end
        if obj == math.huge or obj == -math.huge then return "null" end
        return tostring(obj)
    elseif t == "string" then
        return '"' .. obj:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r') .. '"'
    elseif t == "table" then
        local isArray = #obj > 0 or next(obj) == nil
        for k, _ in pairs(obj) do
            if type(k) ~= "number" then isArray = false; break end
        end
        local parts = {}
        if isArray then
            for i, v in ipairs(obj) do
                table.insert(parts, spaces .. "  " .. serializeJson(v, indent + 1))
            end
            return #parts == 0 and "[]" or "[\n" .. table.concat(parts, ",\n") .. "\n" .. spaces .. "]"
        else
            for k, v in pairs(obj) do
                if v ~= nil then
                    table.insert(parts, spaces .. '  "' .. tostring(k) .. '": ' .. serializeJson(v, indent + 1))
                end
            end
            return #parts == 0 and "{}" or "{\n" .. table.concat(parts, ",\n") .. "\n" .. spaces .. "}"
        end
    else return "null" end
end

local function writeResult(status, payload)
    local outputDir = outputPath:match("(.+)[/\\]") or "."
    local resultPath = outputDir .. "/cleanup_result.json"
    local result = payload or {}
    result.status = status
    result.input_path = inputPath
    result.output_path = outputPath
    local resultJson = serializeJson(result)
    local resultFile = io.open(resultPath, "w")
    if resultFile then resultFile:write(resultJson); resultFile:close() end
end

-- Validate
if inputPath == "" then writeResult("failed", {error_code="MISSING_INPUT"}); return end
if outputPath == "" then writeResult("failed", {error_code="MISSING_OUTPUT"}); return end

local function fileExists(path)
    local f = io.open(path, "r")
    if f then f:close(); return true end
    return false
end

if not fileExists(inputPath) then writeResult("failed", {error_code="NOT_FOUND"}); return end

-- Open image
local sprite = app.open(inputPath)
if not sprite then writeResult("failed", {error_code="OPEN_FAILED"}); return end

local layer = sprite.layers[1]
local frame = sprite.frames[1]
local cel = layer:cel(frame)
if not cel then writeResult("failed", {error_code="NO_CEL"}); sprite:close(); return end

local img = cel.image:clone()
local w, h = img.width, img.height

-- Utility functions
local function getBrightness(r, g, b)
    return 0.299 * r + 0.587 * g + 0.114 * b
end

local function isOutline(px)
    local r = app.pixelColor.rgbaR(px)
    local g = app.pixelColor.rgbaG(px)
    local b = app.pixelColor.rgbaB(px)
    local a = app.pixelColor.rgbaA(px)
    if a < 128 then return false end
    return getBrightness(r, g, b) <= outlineThreshold
end

local function isSimilar(px1, px2)
    local r1, g1, b1, a1 = app.pixelColor.rgbaR(px1), app.pixelColor.rgbaG(px1), app.pixelColor.rgbaB(px1), app.pixelColor.rgbaA(px1)
    local r2, g2, b2, a2 = app.pixelColor.rgbaR(px2), app.pixelColor.rgbaG(px2), app.pixelColor.rgbaB(px2), app.pixelColor.rgbaA(px2)
    if a1 < 10 and a2 < 10 then return true end
    if (a1 < 10) ~= (a2 < 10) then return false end
    return math.abs(r1-r2) <= fillTolerance and math.abs(g1-g2) <= fillTolerance and math.abs(b1-b2) <= fillTolerance
end

-- Create tracking arrays
local removed = {}
for y = 0, h - 1 do
    removed[y] = {}
    for x = 0, w - 1 do removed[y][x] = false end
end

-- STEP 1: Flood-fill from edges
local queue = {}
local visited = {}
for y = 0, h - 1 do visited[y] = {}; for x = 0, w - 1 do visited[y][x] = false end end

-- Add edge pixels
for x = 0, w - 1 do
    table.insert(queue, {x = x, y = 0})
    table.insert(queue, {x = x, y = h - 1})
end
for y = 1, h - 2 do
    table.insert(queue, {x = 0, y = y})
    table.insert(queue, {x = w - 1, y = y})
end

-- Get corner reference colors
local cornerPixels = {
    img:getPixel(0, 0), img:getPixel(w-1, 0),
    img:getPixel(0, h-1), img:getPixel(w-1, h-1)
}

local pixelsToRemove = {}
local queueHead = 1

while queueHead <= #queue do
    local curr = queue[queueHead]
    queueHead = queueHead + 1
    local x, y = curr.x, curr.y
    
    if x < 0 or x >= w or y < 0 or y >= h then goto continue end
    if visited[y][x] then goto continue end
    visited[y][x] = true
    
    local px = img:getPixel(x, y)
    if isOutline(px) then goto continue end
    
    local matchBg = false
    for _, cpx in ipairs(cornerPixels) do
        if isSimilar(px, cpx) then matchBg = true; break end
    end
    
    local alpha = app.pixelColor.rgbaA(px)
    if matchBg or alpha < 128 then
        table.insert(pixelsToRemove, {x = x, y = y})
        removed[y][x] = true
        table.insert(queue, {x = x-1, y = y})
        table.insert(queue, {x = x+1, y = y})
        table.insert(queue, {x = x, y = y-1})
        table.insert(queue, {x = x, y = y+1})
    end
    ::continue::
end

-- STEP 2: Aggressive edge dilation
-- Remove ANY non-outline pixel that is adjacent to removed area
local edgeRemoved = 0

for pass = 1, dilationPasses do
    local newRemovals = {}
    
    for y = 0, h - 1 do
        for x = 0, w - 1 do
            if removed[y][x] then goto next_pixel end
            
            local px = img:getPixel(x, y)
            
            -- KEEP outline pixels no matter what
            if isOutline(px) then goto next_pixel end
            
            -- Check if adjacent to removed pixel (8-directional for better coverage)
            local adjRemoved = false
            local neighbors = {
                {x-1,y}, {x+1,y}, {x,y-1}, {x,y+1},  -- cardinal
                {x-1,y-1}, {x+1,y-1}, {x-1,y+1}, {x+1,y+1}  -- diagonal
            }
            for _, n in ipairs(neighbors) do
                if n[1] >= 0 and n[1] < w and n[2] >= 0 and n[2] < h then
                    if removed[n[2]][n[1]] then adjRemoved = true; break end
                end
            end
            
            -- If adjacent to removed area and NOT an outline, remove it
            if adjRemoved then
                local a = app.pixelColor.rgbaA(px)
                if a > 5 then  -- Not already transparent
                    table.insert(newRemovals, {x = x, y = y})
                end
            end
            
            ::next_pixel::
        end
    end
    
    -- Apply this pass
    for _, pos in ipairs(newRemovals) do
        removed[pos.y][pos.x] = true
        table.insert(pixelsToRemove, pos)
        edgeRemoved = edgeRemoved + 1
    end
    
    -- Stop if no more removals
    if #newRemovals == 0 then break end
end

-- STEP 3: Final cleanup - Remove isolated greenish pixels adjacent to outline
-- These are pixels that might be trapped between outline and transparent area
local isolatedRemoved = 0

local function isGreenish(px)
    local r = app.pixelColor.rgbaR(px)
    local g = app.pixelColor.rgbaG(px)
    local b = app.pixelColor.rgbaB(px)
    local a = app.pixelColor.rgbaA(px)
    if a < 10 then return false end
    -- Green is dominant or dark with green tint
    return (g > r - 15 and g > b - 15 and g > 20) or (a < 200)
end

for y = 0, h - 1 do
    for x = 0, w - 1 do
        if removed[y][x] then goto skip_isolated end
        
        local px = img:getPixel(x, y)
        if isOutline(px) then goto skip_isolated end
        
        -- Check if this pixel is greenish
        if not isGreenish(px) then goto skip_isolated end
        
        -- Check if adjacent to both outline AND transparent/removed area
        local adjOutline = false
        local adjTransparent = false
        local neighbors = {
            {x-1,y}, {x+1,y}, {x,y-1}, {x,y+1},
            {x-1,y-1}, {x+1,y-1}, {x-1,y+1}, {x+1,y+1}
        }
        
        for _, n in ipairs(neighbors) do
            if n[1] >= 0 and n[1] < w and n[2] >= 0 and n[2] < h then
                if removed[n[2]][n[1]] then
                    adjTransparent = true
                else
                    local npx = img:getPixel(n[1], n[2])
                    if isOutline(npx) then adjOutline = true end
                    if app.pixelColor.rgbaA(npx) < 50 then adjTransparent = true end
                end
            else
                -- Edge of image = transparent
                adjTransparent = true
            end
        end
        
        -- Remove if between outline and transparent area
        if adjOutline and adjTransparent then
            table.insert(pixelsToRemove, {x = x, y = y})
            removed[y][x] = true
            isolatedRemoved = isolatedRemoved + 1
        end
        
        ::skip_isolated::
    end
end

-- Apply removals
local transparentColor = app.pixelColor.rgba(0, 0, 0, 0)
local previewColor = app.pixelColor.rgba(255, 0, 0, 128)

for _, pos in ipairs(pixelsToRemove) do
    if previewMode then
        img:drawPixel(pos.x, pos.y, previewColor)
    else
        img:drawPixel(pos.x, pos.y, transparentColor)
    end
end

cel.image = img
sprite:saveCopyAs(outputPath)

writeResult("success", {
    pixels_removed = #pixelsToRemove,
    edge_pixels_removed = edgeRemoved,
    dilation_passes_used = dilationPasses,
    image_width = w,
    image_height = h,
    total_pixels = w * h,
    removal_percentage = (#pixelsToRemove / (w * h)) * 100,
    params = {outline_threshold = outlineThreshold, fill_tolerance = fillTolerance, dilation_passes = dilationPasses}
})

sprite:close()
print("Cleanup v4 complete! Removed: " .. #pixelsToRemove .. " (edge: " .. edgeRemoved .. ")")
