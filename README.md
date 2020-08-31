
# Submod Updater Plugin

A util submod that makes updating other submods easier. The util can automatically check updates for installed (and [registered](https://github.com/Booplicate/MAS-Submods-SubmodUpdaterPlugin#usage)) submods, notify the user about those updates, and even download and install them.

Currently known submods that support this util:
- [YouTube Music](https://github.com/Booplicate/MAS-Submods-YouTubeMusic)
- [Auto Atmos Change](https://github.com/multimokia/MAS-Submod-Auto-Atmos-Change/tree/master/game/Submods/Auto%20Weather%20Change)
- [Night Music](https://github.com/multimokia/MAS-Submod-Nightmusic/tree/master/Night%20Music)

## Installation:
1. Make sure you're running the latest version of MAS.

2. Download [the latest release](https://github.com/Booplicate/MAS-Submods-SubmodUpdaterPlugin/releases/latest) of the submod.

3. The packages should be installed into your `DDLC/` folder. Exactly this folder, you should have `DDLC.exe` there.

## Usage:
**This part is for the developers that want to add support for this util to their submods, the actual end users do not need to do any manipulations - just install this submod.**

To use the full power of the updater, you'll need to define your submod first. After your submod is registered in the submods map, you can define an updater for it. Keep in mind that the name you pass in for the updater must be the same you used when defined your `Submod` object. Example:
```python
# Register the submod
init -990 python:
    store.mas_submod_utils.Submod(
        author="Your Name",
        name="Your Submod Name",
        description="A short description.",
        version="9.2.2",
        settings_pane="settings_screen_for_your_submod"
    )

# Register the updater
init -989 python:
    if store.mas_submod_utils.isSubmodInstalled("Submod Updater Plugin"):
        store.sup_utils.SubmodUpdater(
            submod="Your Submod Name",
            user_name="Your_GitHub_Login",
            repository_name="Name_of_the_Repository_for_Your_Submod"
        )
```
Alternatively, you can pass in the `Submod` object itself instead of its name. Whatever you feel would suit your needs!

There're currently 9 additional parameters you can use:
- `should_notify` - toggles if we should notify the user about updates for this submod. Default `True`.
- `auto_check` - toggles if we should automatically check for updates. Default `True`.
- `allow_updates` - toggles if we should allow the user to update the submod. Default `True`.
- `submod_dir` - the **relative** file path to the directory of your submod. If `None` (default), the updater will try to locate your submod. But if it fails and you've not specified the dir, the updater might fail to download and install updates.
- `update_dir` - directory where updates will be installed in. If `None` (default), the updater will set it to the submod directory, if empty string, updates will be installed in the base directory.
- `extraction_depth` - depth of the recursion for the update extractor. Defaut `1` - updater will try to go one folder inside to unpack updates.
- `attachment_id` - id of the attachment with updates on GitHub. If you attach only one file, it'd be `0`, if two, depending on the order it can be either `0` or `1`. And so on. Defaults to `0`. If `None`, the updater will download **the source files**. Note that GitHub doesn't support distributing releases that way. It will be noticeably slower to download and sometimes may fail to download at all. In short: use attachments.
- `tag_formatter` - if not `None`, assuming it's a function that accepts version tag from github as a string, formats it in a way, and returns a new formatted tag as a string. Exceptions are auto-handled. If `None` (default), no formatting applies on version tags.
- `redirected_files` - a string or a list of strings with filenames that the updater will *try* to move to the submod dir during update. If the files don't exist or this's set to empty list/tuple, it will do nothing. If None this will be set to a tuple of 3 items: `("readme.md", "license.md", "changelog.md")`. Default `None`. This's case-insensitive.

Define your updater at init level `-989`, **after** you defined the submod.
The `store.mas_submod_utils.isSubmodInstalled("Submod Updater Plugin")` check is optional, but it'll allow you to support both versions of your submod: with the updater and without it. On a side note, if you don't do that check and you need to define the updater earlier for some reason, you can init your updater at `-990`.

## API:
Some methods of the `SubmodUpdater` class you can work with.
- `hasUpdate` is the main way to check if there's an update, note that it'll send the request only once per session.
- `_checkUpdate` is an alternative to the method above. It'll rerequest data from GitHub when appropriate. Usually there's no need in that if you have `auto_check` enabled.
- `_checkUpdateInThread` runs `_checkUpdate` in a thread.
- `toggleNotifs`, `toggleAutoChecking`, and `toggleUpdates` allows to easily toggle values of the corresponding properties of the updater.
- `isUpdating` checks whether or not we're updating this submod now.
- `hasUpdated` checks whether or not we've updated this submod.
- `downloadUpdateInThread` allows you to download and install updates. This does not check for an update before downloading, and therefore will do nothing if you've not checked it before (or it wasn't done automatically).
- `getDirectory` returns the path to the submod directory.
- `getDirectoryFor` (class method) checks `getDirectory` for the given submod.
- `hasUpdateFor`(class method) checks `hasUpdate` for the given submod. If submod doesn't exist, return `False` like if there's no update.
- `getUpdater` (class method) returns `SubmodUpdater` object by its name.
- `openURL` (static method) opens an url in the default browser. Safe to use, but you should probably let the user know before opening their browser. Can be used to open the releases page for your submod.
- `openFolder` (static method) like `openURL`, but opens a folder in the default viewer. Can be used to open the game folder, or the folder with your submod. Or whatsoever.

Rarely used methods.
- `_downloadUpdate` is what `downloadUpdateInThread` uses to download updates. Accepts the same args/kwargs.
- `_checkConflicts` - checks if it's safe to update the submod. Return list of tuples with conflicting submod, submod itself, and its max supported version.
- `getUpdatersForOutdatedSubmods` (class method) just what you think - it returns `SubmodUpdater` objects for each outdated submod.
- `hasOutdatedSubmods` (class method) returns boolean whether or not we have outdated submods.
- `isUpdatingAny` (class method) returns boolean whether or not we're updating a submod.
- `isBulkUpdating` (class method) Returns boolean whether or not we have an ongoing bulk update.
- `_notify` (class method) notifies the user about all available updates at once (if the appropriate updater has the `should_notify` property set to `True`).
- `getIcon` (class method) returns an appropriate icon depending on the state of a submod (has update/currently updating).

Properties to access (only `get`) json data. These 5 can be `None` as a fallback, keep that in mind.
- `latest_version` - the latest version of the submod available.
- `update_name` - the name of the latest update.
- `update_changelog` - the changelog for the latest update.
- `update_page_url` - link to the latest release page on GitHub.
- `update_package_url` - link to update attachments

Properties to check status of the update (only `get`).
- `is_updating` - whether we're updating this submod now or not
- `has_updated` - whether we updated this submod or not

Some other properties.
- `id` - id/name of the updater **and** submod.
- `_submod` - pointer to the `Submod` object.
- `should_notify`
- `auto_check`
- `_submod_dir` - relative path to the submod folder.
- `_json` - json data from GitHub (but better use the appropriate properties to access it). Can be `None`. Might return not what you'd expect it to due to threading.
- `_last_update_check` - `datetime.datetime` of the last time we checked for an update. Can be `None`. Might return not what you'd expect it to due to threading.

There are probably some more methods and properties. But it's **highly recommended to avoid using them**. Although, if you're really interested, you'll find them in the sources.

## Some important notes:
The versioning of your submod and the tags you're using on GitHub must have the same format (`0.0.1`), otherwise you'll have to specify the parser via the `tag_formatter` argument.

Requests to GitHub should be done with an interval of no less than 1 hour.

Recommended to have submods in `/game/Submods/`.

The user can install only one update at a time, to apply the changes, they'll need to restart the game.
