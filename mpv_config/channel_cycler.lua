local utils = require 'mp.utils'
local msg = require 'mp.msg'

-- CONFIGURATION
local base_path = utils.join_path(os.getenv("HOME"), "Channels")
local playlist_filename = "playlist.m3u"
local settings_filename = "settings.json"
local history_file = utils.join_path(mp.find_config_file("."), "channel_history.json")

-- STATE
local playlists = {}
local current_index = 0

-- HISTORY TRACKING
-- Stores { index = 0, time = 10.5 } for each playlist path
local channel_history = {}
-- Holds the target state we want to restore after the new playlist loads
local pending_restore = nil 

function file_exists(path)
    local info = utils.file_info(path)
    return info and info.is_file
end

function load_channel_settings(playlist_path)
    local channel_dir = playlist_path:match("(.+)/" .. playlist_filename .. "$")
    if not channel_dir then return nil end

    local settings_path = utils.join_path(channel_dir, settings_filename)
    if not file_exists(settings_path) then return nil end

    local file = io.open(settings_path, "r")
    if not file then return nil end

    local content = file:read("*all")
    file:close()

    local success, data = pcall(utils.parse_json, content)
    if success and data then
        msg.info("Loaded settings for channel: " .. channel_dir)
        return data
    end

    msg.warn("Could not parse settings file: " .. settings_path)
    return nil
end

function apply_channel_settings(settings)
    if not settings then return end

    if settings.volume ~= nil then
        mp.set_property_number("volume", settings.volume)
        msg.info("Set volume to: " .. settings.volume)
    end
end

function load_history()
    if not file_exists(history_file) then
        msg.info("No history file found, starting fresh")
        return
    end

    local file = io.open(history_file, "r")
    if not file then
        msg.warn("Could not open history file: " .. history_file)
        return
    end

    local content = file:read("*all")
    file:close()

    if not content or content == "" then
        msg.warn("History file is empty")
        return
    end

    local success, data = pcall(utils.parse_json, content)
    if success and data then
        channel_history = data
        msg.info("Loaded channel history from: " .. history_file)
    else
        msg.warn("Could not parse history file, starting fresh")
    end
end

function save_history()
    local json = utils.format_json(channel_history)
    if not json then
        msg.warn("Could not serialize history to JSON")
        return
    end

    local file = io.open(history_file, "w")
    if not file then
        msg.warn("Could not open history file for writing: " .. history_file)
        return
    end

    file:write(json)
    file:close()
end

function scan_playlists()
    playlists = {}
    msg.info("Scanning for playlists in: " .. base_path)

    local files = utils.readdir(base_path, "dirs")
    if not files then
        msg.warn("Could not read directory: " .. base_path)
        return
    end

    table.sort(files)

    for _, dir_name in ipairs(files) do
        local channel_dir = utils.join_path(base_path, dir_name)
        local playlist_path = utils.join_path(channel_dir, playlist_filename)

        if file_exists(playlist_path) then
            table.insert(playlists, playlist_path)
        end
    end
end

function save_current_state()
    if current_index == 0 or #playlists == 0 then return end

    local current_path = playlists[current_index]
    -- Get current file index (0-based) and time position
    local pos = mp.get_property_number("playlist-pos")
    local time = mp.get_property_number("time-pos")

    -- Only save if we have valid data (time is sometimes nil at strict start/end)
    if current_path and pos and time then
        channel_history[current_path] = { index = pos, time = time }
        save_history()
    end
end

function cycle_channel(direction)
    -- 1. Save the progress of the CURRENT channel before leaving
    save_current_state()

    if #playlists == 0 then 
        scan_playlists()
        if #playlists == 0 then return end
    end

    -- 2. Calculate new channel index
    current_index = current_index + direction
    if current_index > #playlists then
        current_index = 1
    elseif current_index < 1 then
        current_index = #playlists
    end

    -- 3. Prepare to restore history for the NEW channel
    local next_path = playlists[current_index]
    pending_restore = channel_history[next_path] -- This might be nil if never visited

    -- 4. Load the new playlist
    mp.commandv("loadfile", next_path, "replace")

    -- 5. Apply channel-specific settings (e.g., volume)
    local settings = load_channel_settings(next_path)
    apply_channel_settings(settings)

    -- Display OSD
    local parent_dir = next_path:match("([^/]+)/" .. playlist_filename .. "$")
    mp.osd_message("Channel: " .. (parent_dir or "Unknown"))
end

-- EVENT LISTENER: This runs every time a file loads
-- We use this to intervene and restore position after the playlist loads
mp.register_event("file-loaded", function()
    -- If we don't have a restore target, do nothing (normal playback)
    if not pending_restore then return end

    local current_pos = mp.get_property_number("playlist-pos")
    local count = mp.get_property_number("playlist-count")

    -- Safety check
    if not current_pos or not count or count == 0 then return end

    -- STEP 1: Are we at the right file in the playlist?
    if current_pos ~= pending_restore.index then
        -- We are at the wrong file (usually 0). Switch to the saved index.
        -- Check if the saved index is still valid (e.g. playlist didn't shrink)
        if pending_restore.index < count then
            mp.set_property_number("playlist-pos", pending_restore.index)
        else
            -- Saved index is invalid, clear restore to prevent loops
            pending_restore = nil
        end
        -- We return here. Changing 'playlist-pos' triggers a new load, 
        -- so this function will run again for the correct file.
        return 
    end

    -- STEP 2: We are at the right file. Now seek to the time.
    if pending_restore.time > 0 then
        mp.set_property_number("time-pos", pending_restore.time)
    end
    
    -- Restore complete, clear the pending flag
    pending_restore = nil
end)

-- Initialize
load_history()
scan_playlists()

-- Bindings
mp.add_key_binding(nil, "channel-next", function() cycle_channel(1) end)
mp.add_key_binding(nil, "channel-prev", function() cycle_channel(-1) end)
mp.add_key_binding(nil, "channel-refresh", scan_playlists)

-- Save position periodically (every 10 seconds) to ensure it's captured
mp.add_periodic_timer(10, function()
    save_current_state()
end)

-- Also try to save on various exit-related events
mp.register_event("shutdown", function()
    save_current_state()
end)

mp.register_event("end-file", function()
    save_current_state()
end)

-- Optional: Auto-start first channel
if #playlists > 0 then
    cycle_channel(1)
end