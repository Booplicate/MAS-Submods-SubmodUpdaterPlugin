
# Submod Updater Plugin

A util submod that makes updating other submods easier. The util can automatically check updates for installed (and [registered](https://github.com/Booplicate/MAS-Submods-SubmodUpdaterPlugin#usage)) submods, notify the user about those updates, and even download and install them.

**You do not need this unless you're a developer, or you were asked to install this as a dependency for another submod.**

## Permissions:
You're free to use this for making and supporting submods (modificaion) for [Monika After Story](https://github.com/Monika-After-Story/MonikaModDev). You're also allowed to ship the releases of this util with those submods. I'd really appreciate if you leave a link to this repository and mention me as the author of this tool.

## Installation:
0. Make sure you're running the latest version of MAS.

1. Download the latest release of the submod from [the releases page](https://github.com/Booplicate/MAS-Submods-SubmodUpdaterPlugin/releases).

2. The packages should be installed into your `DDLC/` folder. Exactly this folder, you should have `DDLC.exe` there.

## Usage:
To use the full power of the updater, you'll need to define your submod first. After your submod is registered in the submods map, you can define an updater. Keep in mind that the name you pass in for the updater must be the same you used when defined your `Submod` object. Example:
```python
# Register the submod
init -990 python in mas_submod_utils:
    Submod(
        author="Your Name",
        name="Your Submod Name",
        description="A short description.",
        version="9.2.2",
        settings_pane="settings_screen_for_your_submod"
    )

# Register the updater
init -980 python in sup_utils:
    SubmodUpdater(
        submod="Your Submod Name",
        user_name="Your_GitHub_Login",
        repository_name="Name_of_the_Repository_for_Your_Submod"
    )
```
Alternatively, you can pass in the `Submod` object itself instead of its name. Whatever you feel would suit your needs!

There're currently 5 additional parameters you can use:
- `should_notify` - toggles if we should notify the user about updates for this submod. Default `True`.
- `auto_check` - toggles if we should automatically check for updates. Default `True`.
- `attachment_id` - id of the attachment with updates on GitHub. If you attach only one file, it'd be `0`, if two, depending on the order it can be either `0` or `1`. And so on. Defaults to `0`. If `None`, the updater will download **the source files**.
- `submod_dir` - the **relative** file path to the directory of your submod. If `None` (default), the updater will try to locate your submod. But if it fails and you've not specified the path, the updater won't be able to download and install updates.
- `raise_critical` - whether or not we raise **critical** exceptions. Those are raised when the user has issues with the game files, which should be **manually** moved/deleted/etc. Default `True`.

There's no strict rule when you should define your updater, you can do it from init level `-980` upto `999`. But for consistency and stability, I'd suggest to do it as early as possible - `-980`.

## API:
Some methods of the `SubmodUpdater` class you can work with.
- `isUpdateAvailable` is the main way to check if there's an update, note that it'll send the request only once per session.
- `_checkUpdate` is an alternative to the method above. It'll rerequest data from GitHub when appropriate. Usually there's no need in that if you have `auto_check` enabled.
- `_checkUpdateInThread` runs `_checkUpdate` in a thread.
- `toggleNotifs` and `toggleAutoChecking` allows to easily toggle values of the corresponding properties of the updater.
- `downloadUpdateInThread` allows you to download and install updates. This does not check for an update before downloading, and therefore will do nothing if you've not checked it before (or it wasn't done automatically). **IMPORTANT NOTE**: downloading and installing updates is a new feature that may or may not cause unpredictable issues. **Please let me know if you found any bugs**. Recommended to use with `raise_critical` set to `True`.
- `hasUpdateFor`(class method) checks `isUpdateAvailable` for the given submod. If submod doesn't exist, return `False` like if there's no update.
- `getIcon` (class method) returns the appropriate icon depending on the state of a submod (has update/currently updating). Use this in your submod setting screen via the `add` statement.
- `getUpdater` (class method) returns `SubmodUpdater` object by its name.
- `openURL` (static method) opens an url in the default browser. Safe to use, but you probably should let the user know before opening their browser. Can be used to open the releases page for your submod.
- `openFolder` (static method) like `openURL`, but opens a folder in the default viewer. Can be used to open the game folder, or the folder with your submod. Or whatsoever.

Rarely used methods.
- `_downloadUpdate` is what `downloadUpdateInThread` uses to download updates. Accepts the same args/kwargs.
- `getUpdatersForOutdatedSubmods` (class method) just what you think - it returns `SubmodUpdater` objects for each outdated submod.
- `hasOutdatedSubmods` (class method) returns whether we have outdated submods.
- `_isUpdatingAny` (class method) whether or not we're updating something.
- `_notify` (class method) notifies the user about all available updates at once (if the appropriate updater has the `should_notify` property set to `True`).

Properties to access (only `get`) json data. These 5 can be `None` as a fallback, keep that in mind.
- `latest_version` - the latest version of the submod available.
- `update_name` - the name of the latest update.
- `update_changelog` - the changelog for the latest update.
- `update_page_url` - link to the latest release page on GitHub.
- `update_package_url` - link to update attachments

Some other properties.
- `id` - id/name of the updater **and** submod.
- `_submod` - pointer to the `Submod` object.
- `should_notify`
- `auto_check`
- `_submod_dir` - relative path to the submod folder.
- `has_updated` - whether or not we updated this submod
- `_json` - json data from GitHub (but better use the appropriate properties to access it). Can be `None`. Might return not what you'd expect it to due to threading.
- `_last_update_check` - `datetime.datetime` of the last time we checked for an update. Can be `None`. Might return not what you'd expect it to due to threading.

There're probably some more methods and properties. But it's **highly recommended to avoid using them**. Although, if you're really interested, you can read the sources.

The tool also allows you to use the confirmation screen `sup_confirm_screen` in your submods. It takes 3 arguments: `message` - the message to display, `yes_action` - the action to do when the user presses the `Yes` button (Default: `NullAction`), and `no_action` - the action to do when the user presses the `No` button (Default: `Hide("sup_confirm_screen")` [which will hide the screen]).
