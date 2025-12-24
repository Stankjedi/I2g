--[[
    convert_sheet_to_anim.lua
    Core Lua script for Aseprite spritesheet to animation conversion.
    
    Called via: aseprite -b --script-param key=value ... --script convert_sheet_to_anim.lua
    
    Parameters (via app.params):
      - input_path: Path to input spritesheet PNG
      - output_dir: Output directory for results
      - job_name: Name for this job
      - grid_rows, grid_cols: Grid dimensions
      - grid_offset_x, grid_offset_y: Grid offset
      - grid_pad_x, grid_pad_y: Grid padding
      - fps: Frames per second
      - loop_mode: "loop" or "pingpong"
      - anchor_mode: "foot", "center", or "none"
      - anchor_alpha_thresh: Alpha threshold for opaque detection
      - bg_mode: "transparent", "keep", or "color"
      - bg_color_r/g/b: Background color RGB
      - bg_tolerance: Color matching tolerance
      - export_aseprite: "true"/"false"
      - export_sheet: "true"/"false"
      - export_gif: "true"/"false"
      - sheet_padding_border, sheet_padding_inner: Sheet export padding
      - trim: "true"/"false"
    
    Outputs:
      - anim.aseprite (if export_aseprite)
      - anim_sheet.png + anim_sheet.json (if export_sheet)
      - anim_preview.gif (if export_gif)
      - meta.json (always)
]]

-- Parse parameters
local function getParam(name, default)
    local val = app.params[name]
    if val == nil or val == "" then
        return default
    end
    return val
end

local function getParamNumber(name, default)
    local val = app.params[name]
    if val == nil or val == "" then
        return default
    end
    return tonumber(val) or default
end

local function getParamBool(name, default)
    local val = app.params[name]
    if val == nil or val == "" then
        return default
    end
    return val == "true" or val == "1"
end

-- Parameters
local inputPath = getParam("input_path", "")
local outputDir = getParam("output_dir", "")
local jobName = getParam("job_name", "anim")

local gridRows = getParamNumber("grid_rows", 1)
local gridCols = getParamNumber("grid_cols", 1)
local gridOffsetX = getParamNumber("grid_offset_x", 0)
local gridOffsetY = getParamNumber("grid_offset_y", 0)
local gridPadX = getParamNumber("grid_pad_x", 0)
local gridPadY = getParamNumber("grid_pad_y", 0)

local fps = getParamNumber("fps", 12)
local loopMode = getParam("loop_mode", "loop")

local anchorMode = getParam("anchor_mode", "foot")
local anchorAlphaThresh = getParamNumber("anchor_alpha_thresh", 10)

local bgMode = getParam("bg_mode", "transparent")
local bgR = getParamNumber("bg_color_r", 255)
local bgG = getParamNumber("bg_color_g", 255)
local bgB = getParamNumber("bg_color_b", 255)
local bgTolerance = getParamNumber("bg_tolerance", 8)

local exportAseprite = getParamBool("export_aseprite", true)
local exportSheet = getParamBool("export_sheet", true)
local exportGif = getParamBool("export_gif", true)
local sheetPaddingBorder = getParamNumber("sheet_padding_border", 2)
local sheetPaddingInner = getParamNumber("sheet_padding_inner", 2)
local doTrim = getParamBool("trim", false)

-- Simple JSON serialization (for meta.json)
local function serializeJson(obj, indent)
    indent = indent or 0
    local spaces = string.rep("  ", indent)
    local t = type(obj)

    if t == "nil" then
        return "null"
    elseif t == "boolean" then
        return tostring(obj)
    elseif t == "number" then
        if obj ~= obj then return "null" end  -- NaN
        if obj == math.huge or obj == -math.huge then return "null" end
        return tostring(obj)
    elseif t == "string" then
        return '"' .. obj:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r') .. '"'
    elseif t == "table" then
        -- Check if array
        local isArray = #obj > 0 or next(obj) == nil
        for k, _ in pairs(obj) do
            if type(k) ~= "number" then
                isArray = false
                break
            end
        end

        local parts = {}
        if isArray then
            for i, v in ipairs(obj) do
                table.insert(parts, spaces .. "  " .. serializeJson(v, indent + 1))
            end
            if #parts == 0 then
                return "[]"
            end
            return "[\n" .. table.concat(parts, ",\n") .. "\n" .. spaces .. "]"
        else
            for k, v in pairs(obj) do
                if v ~= nil then
                    table.insert(parts, spaces .. '  "' .. tostring(k) .. '": ' .. serializeJson(v, indent + 1))
                end
            end
            if #parts == 0 then
                return "{}"
            end
            return "{\n" .. table.concat(parts, ",\n") .. "\n" .. spaces .. "}"
        end
    else
        return "null"
    end
end

local function paramsSnapshot()
    return {
        input_path = inputPath,
        output_dir = outputDir,
        job_name = jobName,
        grid = {
            rows = gridRows,
            cols = gridCols,
            offset_x = gridOffsetX,
            offset_y = gridOffsetY,
            pad_x = gridPadX,
            pad_y = gridPadY
        },
        timing = {
            fps = fps,
            loop_mode = loopMode
        },
        anchor = {
            mode = anchorMode,
            alpha_thresh = anchorAlphaThresh
        },
        background = {
            mode = bgMode,
            color = {bgR, bgG, bgB},
            tolerance = bgTolerance
        },
        export = {
            aseprite = exportAseprite,
            sheet = exportSheet,
            gif = exportGif,
            sheet_padding_border = sheetPaddingBorder,
            sheet_padding_inner = sheetPaddingInner,
            trim = doTrim
        }
    }
end

local function writeMeta(status, payload)
    if outputDir == nil or outputDir == "" then
        return false
    end

    local metaPath = outputDir .. "/meta.json"
    local meta = payload or {}
    meta.status = status
    if meta.error_code == nil then meta.error_code = "" end
    if meta.error_message == nil then meta.error_message = "" end
    if meta.params == nil then meta.params = paramsSnapshot() end

    local metaJson = serializeJson(meta)
    local metaFile = io.open(metaPath, "w")
    if metaFile then
        metaFile:write(metaJson)
        metaFile:close()
        return true
    end
    return false
end

-- Validate required parameters
if inputPath == "" then
    print("Error: input_path is required")
    writeMeta("failed", { error_code = "MISSING_INPUT_PATH", error_message = "input_path is required" })
    return
end

if outputDir == "" then
    print("Error: output_dir is required")
    writeMeta("failed", { error_code = "MISSING_OUTPUT_DIR", error_message = "output_dir is required" })
    return
end

-- Utility: Check if file exists
local function fileExists(path)
    local file = io.open(path, "r")
    if file then
        file:close()
        return true
    end
    return false
end

-- Utility: Create output paths
local outputAseprite = outputDir .. "/anim.aseprite"
local outputSheetPng = outputDir .. "/anim_sheet.png"
local outputSheetJson = outputDir .. "/anim_sheet.json"
local outputGif = outputDir .. "/anim_preview.gif"
local outputMeta = outputDir .. "/meta.json"

-- Check input exists
if not fileExists(inputPath) then
    print("Error: Input file not found: " .. inputPath)
    writeMeta("failed", { error_code = "INPUT_NOT_FOUND", error_message = "Input file not found: " .. inputPath })
    return
end

-- Open the spritesheet image
local sourceSprite = app.open(inputPath)
if not sourceSprite then
    print("Error: Failed to open image: " .. inputPath)
    writeMeta("failed", { error_code = "SPRITE_OPEN_FAILED", error_message = "Failed to open image: " .. inputPath })
    return
end

-- Get image dimensions
local imgWidth = sourceSprite.width
local imgHeight = sourceSprite.height

-- Calculate frame dimensions
local frameWidth = math.floor((imgWidth - gridOffsetX - gridPadX * (gridCols - 1)) / gridCols)
local frameHeight = math.floor((imgHeight - gridOffsetY - gridPadY * (gridRows - 1)) / gridRows)

if frameWidth <= 0 or frameHeight <= 0 then
    print("Error: Invalid frame dimensions calculated")
    writeMeta("failed", { error_code = "INVALID_FRAME_DIMENSIONS", error_message = "Invalid frame dimensions calculated" })
    sourceSprite:close()
    return
end

-- Import spritesheet using Aseprite's ImportSpriteSheet command
app.command.ImportSpriteSheet {
    ui = false,
    type = SpriteSheetType.ROWS,  -- Import row by row, left to right
    frameBounds = Rectangle(gridOffsetX, gridOffsetY, frameWidth, frameHeight),
    padding = Size(gridPadX, gridPadY),
    partialTiles = false
}

-- Now sourceSprite has been split into frames
local frameCount = #sourceSprite.frames

if frameCount == 0 then
    print("Error: No frames after import")
    writeMeta("failed", { error_code = "NO_FRAMES_AFTER_IMPORT", error_message = "No frames after import" })
    sourceSprite:close()
    return
end

-- Calculate frame duration from FPS
local frameDurationMs = math.floor(1000 / fps)

-- Set all frames to same duration
for i, frame in ipairs(sourceSprite.frames) do
    frame.duration = frameDurationMs / 1000.0  -- Aseprite uses seconds
end

-- Background removal (color matching replacement)
local function removeBackground(sprite)
    if bgMode ~= "transparent" then
        return
    end
    
    -- For each frame
    for i, frame in ipairs(sprite.frames) do
        local cel = sprite.layers[1]:cel(frame)
        if cel then
            local img = cel.image:clone()
            local w = img.width
            local h = img.height
            
            -- Current approach: replace pixels that match the configured background color (with tolerance).
            -- Future improvement: edge flood-fill to remove only connected background regions.
            
            for y = 0, h - 1 do
                for x = 0, w - 1 do
                    local px = img:getPixel(x, y)
                    local r = app.pixelColor.rgbaR(px)
                    local g = app.pixelColor.rgbaG(px)
                    local b = app.pixelColor.rgbaB(px)
                    local a = app.pixelColor.rgbaA(px)
                    
                    -- Check if matches background color
                    if math.abs(r - bgR) <= bgTolerance and
                       math.abs(g - bgG) <= bgTolerance and
                       math.abs(b - bgB) <= bgTolerance then
                        img:drawPixel(x, y, app.pixelColor.rgba(0, 0, 0, 0))
                    end
                end
            end
            
            cel.image = img
        end
    end
end

-- Anchor alignment (foot mode)
local function alignAnchors(sprite)
    if anchorMode == "none" then
        return {}, 0, 0
    end
    
    local offsets = {}
    local anchors = {}
    
    -- Calculate anchor point for each frame
    for i, frame in ipairs(sprite.frames) do
        local cel = sprite.layers[1]:cel(frame)
        if cel then
            local img = cel.image
            local w = img.width
            local h = img.height
            local celX = cel.position.x
            local celY = cel.position.y
            
            local anchorX = w / 2
            local anchorY = h
            
            if anchorMode == "foot" then
                -- Find baseline (lowest non-transparent row)
                local baseline = -1
                for y = h - 1, 0, -1 do
                    for x = 0, w - 1 do
                        local px = img:getPixel(x, y)
                        local a = app.pixelColor.rgbaA(px)
                        if a > anchorAlphaThresh then
                            baseline = y
                            break
                        end
                    end
                    if baseline >= 0 then break end
                end
                
                if baseline >= 0 then
                    -- Find center X at baseline
                    local xPositions = {}
                    for y = math.max(0, baseline - 2), baseline do
                        for x = 0, w - 1 do
                            local px = img:getPixel(x, y)
                            local a = app.pixelColor.rgbaA(px)
                            if a > anchorAlphaThresh then
                                table.insert(xPositions, x + celX)
                            end
                        end
                    end
                    
                    if #xPositions > 0 then
                        table.sort(xPositions)
                        anchorX = xPositions[math.floor(#xPositions / 2) + 1]
                    else
                        anchorX = celX + w / 2
                    end
                    anchorY = baseline + celY
                else
                    anchorX = celX + w / 2
                    anchorY = celY + h
                end
            elseif anchorMode == "center" then
                -- Find bounding box center
                local minX, minY, maxX, maxY = w, h, 0, 0
                for y = 0, h - 1 do
                    for x = 0, w - 1 do
                        local px = img:getPixel(x, y)
                        local a = app.pixelColor.rgbaA(px)
                        if a > anchorAlphaThresh then
                            minX = math.min(minX, x)
                            minY = math.min(minY, y)
                            maxX = math.max(maxX, x)
                            maxY = math.max(maxY, y)
                        end
                    end
                end
                
                if maxX >= minX and maxY >= minY then
                    anchorX = celX + (minX + maxX) / 2
                    anchorY = celY + (minY + maxY) / 2
                else
                    anchorX = celX + w / 2
                    anchorY = celY + h / 2
                end
            end
            
            table.insert(anchors, {x = anchorX, y = anchorY, frame = i})
        end
    end
    
    if #anchors == 0 then
        return {}, 0, 0
    end
    
    -- Calculate target anchor (median of all anchors)
    local xVals = {}
    local yVals = {}
    for _, a in ipairs(anchors) do
        table.insert(xVals, a.x)
        table.insert(yVals, a.y)
    end
    table.sort(xVals)
    table.sort(yVals)
    
    local targetX = xVals[math.floor(#xVals / 2) + 1]
    local targetY = yVals[math.floor(#yVals / 2) + 1]
    
    -- Calculate offsets needed to align each frame
    for i, a in ipairs(anchors) do
        local dx = math.floor(targetX - a.x)
        local dy = math.floor(targetY - a.y)
        table.insert(offsets, {dx = dx, dy = dy})
    end
    
    -- Apply offsets by moving cels
    -- First, we need to expand canvas to accommodate all shifts
    local maxLeft = 0
    local maxUp = 0
    local maxRight = 0
    local maxDown = 0
    
    for _, o in ipairs(offsets) do
        if o.dx < 0 then maxLeft = math.max(maxLeft, -o.dx) end
        if o.dx > 0 then maxRight = math.max(maxRight, o.dx) end
        if o.dy < 0 then maxUp = math.max(maxUp, -o.dy) end
        if o.dy > 0 then maxDown = math.max(maxDown, o.dy) end
    end
    
    -- Expand canvas
    if maxLeft > 0 or maxUp > 0 or maxRight > 0 or maxDown > 0 then
        app.command.CanvasSize {
            ui = false,
            left = maxLeft,
            top = maxUp,
            right = maxRight,
            bottom = maxDown,
            trimOutside = false
        }
        
        -- Adjust target for canvas expansion
        targetX = targetX + maxLeft
        targetY = targetY + maxUp
    end
    
    -- Move each cel
    for i, frame in ipairs(sprite.frames) do
        local cel = sprite.layers[1]:cel(frame)
        if cel and offsets[i] then
            local newPos = Point(
                cel.position.x + offsets[i].dx + maxLeft,
                cel.position.y + offsets[i].dy + maxUp
            )
            cel.position = newPos
        end
    end
    
    return offsets, targetX, targetY
end

-- Calculate quality metrics
local function calculateQualityMetrics(offsets)
    if #offsets == 0 then
        return 0, 0, 0
    end
    
    -- Calculate jitter RMS
    local sumSq = 0
    for _, o in ipairs(offsets) do
        sumSq = sumSq + o.dx * o.dx + o.dy * o.dy
    end
    local jitterRms = math.sqrt(sumSq / #offsets)
    
    return jitterRms, 0, 0
end

-- Process the sprite
removeBackground(sourceSprite)
local offsets, targetX, targetY = alignAnchors(sourceSprite)
local jitterRms, baselineVar, bboxVar = calculateQualityMetrics(offsets)

-- Export outputs

-- 1. Export .aseprite file
if exportAseprite then
    sourceSprite:saveCopyAs(outputAseprite)
end

-- 2. Export spritesheet PNG + JSON
if exportSheet then
    app.command.ExportSpriteSheet {
        ui = false,
        askOverwrite = false,
        type = SpriteSheetType.ROWS,
        textureFilename = outputSheetPng,
        dataFilename = outputSheetJson,
        dataFormat = SpriteSheetDataFormat.JSON_ARRAY,
        borderPadding = sheetPaddingBorder,
        shapePadding = sheetPaddingInner,
        innerPadding = 0,
        trim = doTrim,
        extrude = false,
        openGenerated = false,
        layer = "",
        tag = "",
        splitLayers = false,
        listLayers = true,
        listTags = true,
        listSlices = true
    }
end

-- 3. Export GIF preview
if exportGif then
    sourceSprite:saveCopyAs(outputGif)
end

-- 4. Write meta.json
local offsetsList = {}
for _, o in ipairs(offsets) do
    table.insert(offsetsList, {o.dx, o.dy})
end

local meta = {
    status = "success",
    error_code = "",
    error_message = "",
    params = paramsSnapshot(),
    job_name = jobName,
    frame_count = frameCount,
    fps = fps,
    loop_mode = loopMode,
    grid = {
        rows = gridRows,
        cols = gridCols,
        offset_x = gridOffsetX,
        offset_y = gridOffsetY,
        pad_x = gridPadX,
        pad_y = gridPadY,
        frame_width = frameWidth,
        frame_height = frameHeight
    },
    anchor = {
        mode = anchorMode,
        target_x = math.floor(targetX),
        target_y = math.floor(targetY),
        per_frame_offsets = offsetsList
    },
    quality = {
        anchor_jitter_rms_px = jitterRms,
        baseline_var_px = baselineVar,
        bbox_var = bboxVar
    },
    outputs = {
        aseprite = exportAseprite and "anim.aseprite" or nil,
        sheet_png = exportSheet and "anim_sheet.png" or nil,
        sheet_json = exportSheet and "anim_sheet.json" or nil,
        gif = exportGif and "anim_preview.gif" or nil
    },
    source = {
        path = inputPath,
        width = imgWidth,
        height = imgHeight
    }
}

writeMeta("success", meta)

-- Close sprite
sourceSprite:close()

print("Conversion complete: " .. jobName)
print("  Frames: " .. frameCount)
print("  Anchor jitter RMS: " .. string.format("%.2f", jitterRms) .. " px")
