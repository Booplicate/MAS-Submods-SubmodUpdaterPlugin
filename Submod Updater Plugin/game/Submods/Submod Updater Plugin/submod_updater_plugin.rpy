
# Register the submod
init -990 python in mas_submod_utils:
    Submod(
        author="Booplicate",
        name="Submod Updater Plugin",
        description=(
            "A util submod that makes updating other submods easier. "
            "More information on the project's {a=https://github.com/Booplicate/MAS-Submods-SubmodsUpdaterPlugin}{i}{u}GitHub{/u}{/i}{/a}."
        ),
        version="1.0",
        settings_pane="sup_setting_pane"
    )

# Register the updater
init -980 python in sup_utils:
    SubmodUpdater(
        submod="Submod Updater Plugin",
        user_name="Booplicate",
        repository_name="MAS-Submods-SubmodsUpdaterPlugin"
    )

# # # SUBMODUPDATER CLASS
init -981 python in sup_utils:
    import store.mas_submod_utils as mas_submod_utils
    import store.mas_utils as mas_utils
    import re
    import os
    import datetime
    import time
    import urllib2
    import threading
    from json import loads as loadJSON
    from zipfile import ZipFile
    from shutil import rmtree as removeFolders
    from subprocess import Popen as subprocOpen
    from webbrowser import open as openBrowser

    SubmodError = mas_submod_utils.SubmodError

    class SubmodUpdater(object):
        """
        Submod Updater

        PROPERTIES:
            public:
                id - id/name of the updater and the submod
                submod - pointer to the submod object
                should_notify - whether or not we notify the user about updates
                auto_check - whether or not we automically check for updates
                submod_dir - the relative file path to the submod directory
                json - json data about submod from GitHub
                last_update_check - datetime.datetime the last time we checked for update
                update_available - whether or not we have an update available

            private:
                user_name - the author's user name on GitHub
                repository_name - the submod's GitHub repository name
                attachment_id - id of the attachment on GitHub (usually 0)
                raise_critical - flag whether or not we raise CRITICAL exceptions
                updating - flag whether or not we're currently updating the submod
                updated - flag whether was the submod updated
        """
        # url parts
        URL_API = "https://api.github.com/"
        URL_REPOS = "repos/"
        URL_LATEST_RELEASE = "/releases/latest"

        # DO NOT change this
        HEADERS = {
            "User-Agent": "Just Monika! (Monika After Story v{0})".format(renpy.config.version),
            "Accept-Language": "en-US",
            "Content-Language": "en-US",
            "Accept-Charset": "utf8"
        }

        # the interval between requests
        REQUESTS_INTERVAL = datetime.timedelta(hours=1)

        # IO file chunks
        REQUEST_CHUNK = 5242880
        WRITING_CHUNK = 262144

        # lock for threading stuff
        updateDownloadLock = threading.Lock()

        # normalized path of the game directory
        GAME_FOLDER = renpy.config.basedir.replace("\\", "/")

        FOLDER_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_]")

        # html codes
        OK_CODE = 200
        RATE_LIMIT_CODE = 403

        # a map of submods which we will check for updates
        registered_updaters = dict()

        def __init__(self, submod, user_name, repository_name, should_notify=True, auto_check=True, attachment_id=0, submod_dir=None, raise_critical=True):
            """
            Constructor

            IN:
                submod - either the name of the submod
                    or the Submod object itself

                user_name - the author's user name (login) on GitHub

                repository_name - the submod's GitHub repository name

                should_notify - whether or not we notify the user about updates
                    (Default: True)

                auto_check - whether or not we automically check for updates (this's not auto updating)
                    (Default: True)

                attachment_id - id of the attachment on GitHub
                    (only if you have more than one attachment in releases, not counting source code)
                    NOTE: if set to None, the updater will download the source files
                    (Default: 0)

                submod_dir - the relative file path to the directory of the submod
                    e.g. 'game/.../your submod folder'
                    NOTE: if None, the updater will try to find the path itself
                    NOTE: if None when we're trying to update the submod, the update will be aborted
                    (Default: None)

                raise_critical - whether or not we raise CRITICAL exceptions
                    e.g. when we know that there're files that should be MANUALLY deleted due to an error
                    (Default: True)
            """
            if isinstance(submod, basestring):
                submod_name = submod
                submod_obj = mas_submod_utils.submod_map.get(submod, None)

            elif isinstance(submod, mas_submod_utils.Submod):
                submod_name = submod.name
                submod_obj = mas_submod_utils.submod_map.get(submod.name, None)

            else:
                raise SubmodError(
                    "\"{0}\" is not a string, nor a Submod object.".format(submod)
                )
                return

            if submod_obj is None:
                self.__writeLog("Submod '{0}' had not been registered in MAS Submods Framwork. Ignoring.".format(submod_name))
                return

            if submod_name in self.registered_updaters:
                self.__writeLog("Submod '{0}' had already been registered in Submod Updater Plugin. Ignoring.".format(submod_name))
                return

            self.id = submod_name
            self._submod = submod_obj
            self.__user_name = user_name
            self.__repository_name = repository_name
            self.should_notify = should_notify
            self.auto_check = auto_check
            self.__attachment_id = attachment_id
            self._submod_dir = submod_dir or self.__getFilePath()
            self.__raise_critical = raise_critical

            self.__json_request = self.__buildJSONRequest()
            self._json = None
            self._last_update_check = None
            self._update_available = None
            self.__updated = False
            self.__updating = False

            self.__updateCheckLock = threading.Lock()
            self.__updateAvailablePropLock = threading.Lock()
            self.__updatingPropLock = threading.Lock()
            self.__updatedPropLock = threading.Lock()

            self.registered_updaters[self.id] = self

        @property
        def latest_version(self):
            """
            Returns the latest version number (tag)
            for this submod
            NOTE: can return None if there's no update,
                or we got an exception somewhere
            """
            if self._json:
                return self._json["latest_version"]
            return None

        @property
        def update_name(self):
            """
            Returns the name of the latest update
            for this submod
            NOTE: can return None if there's no update,
                or we got an exception somewhere
            """
            if self._json:
                return self._json["update_name"]
            return None

        @property
        def update_changelog(self):
            """
            Returns the changelog for the latest update
            for this submod
            NOTE: can return None if there's no update,
                or we got an exception somewhere
            """
            if self._json:
                return self._json["update_changelog"]
            return None

        @property
        def update_page_url(self):
            """
            Returns a link to update page
            NOTE: can return None if there's no update,
                or we got an exception somewhere
            """
            if self._json:
                return self._json["update_page_url"]
            return None

        @property
        def update_package_url(self):
            """
            Returns a link to update files
            NOTE: can return None if there's no update,
                or we got an exception somewhere
            """
            if self._json:
                return self._json["update_package_url"]
            return None

        @property
        def has_updated(self):
            """
            Returns a bool whether we updated this submod
            """
            with self.__updatedPropLock:
                value = self.__updated
            return value

        def toggleNotifs(self):
            """
            Toggles the should_notify property
            """
            self.should_notify = not self.should_notify

        def toggleAutoChecking(self):
            """
            Toggles the auto_check property
            """
            self.auto_check = not self.auto_check

        def __getFilePath(self):
            """
            Return a relative filepath to the submod

            OUT:
                string with the filepath,
                or None if we weren't able to get it
            """
            path = renpy.get_filename_line()[0].rpartition("/")[0]
            return path if path else None

        def __buildJSONRequest(self):
            """
            Builds a request object to use later
            for requesting json data from GitHub API

            OUT:
                Request object
            """
            return urllib2.Request(
                url="{}{}{}{}{}{}".format(
                    self.URL_API,
                    self.URL_REPOS,
                    self.__user_name,
                    "/",
                    self.__repository_name,
                    self.URL_LATEST_RELEASE
                ),
                headers=self.HEADERS
            )

        def __requestJSON(self):
            """
            Requests JSON data for latest release

            OUT:
                json data as a dict
            """
            response = None

            try:
                response = urllib2.urlopen(
                    self.__json_request,
                    timeout=15
                )

            except urllib2.HTTPError as e:
                if e.code == self.RATE_LIMIT_CODE:
                    self.__writeLog("Too many requests. Try again later.", e)

                else:
                    self.__writeLog("Failed to request JSON data.", e)

                return None

            except Exception as e:
                self.__writeLog("Failed to request JSON data.", e)
                return None

            if (
                response is not None
                and response.getcode() == self.OK_CODE
            ):
                raw_data = response.read()

                try:
                    json_data = loadJSON(raw_data)

                except Exception as e:
                    self.__writeLog("Failed to load JSON data.", e)
                    return None

                return json_data

            return None

        def __parseJSON(self, json_data):
            """
            Parses JSON data to get the bits we need

            IN:
                json_data - the data to parse

            OUT:
                dict with parsed data:
                    latest_version (Fallback: current submod ver)
                    update_name (Fallback: 'Unknown')
                    update_changelog (Fallback: an empty str)
                    update_page_url (Fallback: None)
                    update_package_url (Fallback: None)
                or None if was incorrect input
            """
            # sanity check
            if not json_data:
                return None

            latest_version = json_data.get("tag_name", None)
            if latest_version is None:
                self.__writeLog("Failed to parse JSON data: missing the 'tag_name' field.")
                latest_version = self._submod.version

            update_name = json_data.get("name", None)
            if update_name is None:
                self.__writeLog("Failed to parse JSON data: missing the 'name' field.")
                update_name = "Unknown"

            update_changelog = json_data.get("body", None)
            if update_changelog is None:
                self.__writeLog("Failed to parse JSON data: missing the 'body' field.")
                update_changelog = ""

            update_page_url = json_data.get("html_url", None)
            if update_page_url is None:
                self.__writeLog("Failed to parse JSON data: missing the 'html_url' field.")

            update_package_url = None
            if self.__attachment_id is not None:
                assets = json_data.get("assets", None)

                if assets is not None:
                    try:
                        update_package_url = assets[self.__attachment_id].get("browser_download_url", None)

                    except IndexError:
                        self.__writeLog("Failed to parse JSON data: attachment with id '{0}' doesn't exist.".format(self.__attachment_id))

                else:
                    self.__writeLog("Failed to parse JSON data: missing the 'assets' field.")

            else:
                update_package_url = json_data.get("zipball_url", None)

                if update_package_url is None:
                    self.__writeLog("Failed to parse JSON data: missing the 'zipball_url' field.")

            return {
                "latest_version": latest_version,
                "update_name": update_name,
                "update_changelog": update_changelog,
                "update_page_url": update_page_url,
                "update_package_url": update_package_url
            }

        def _checkUpdate(self, bypass=False):
            """
            Checks for updates for this submod
            This will also update the json property with a new json if available

            IN:
                bypass - whether or not we should try to bypass the limit
                    NOTE: DANGEROUS
                    (Default: False)

            OUT:
                True if we have an update, False otherwise
            """
            with self.__updateCheckLock:
                _now = datetime.datetime.now()

                # TT protection
                if (
                    self._last_update_check is not None
                    and _now < self._last_update_check
                ):
                    self._last_update_check = _now

                with self.__updateAvailablePropLock:
                    temp_value = self._update_available

                # if we checked for update recently, we'll skip this check
                if (
                    bypass
                    or self._last_update_check is None
                    or (
                        self._last_update_check is not None
                        and _now - self._last_update_check > self.REQUESTS_INTERVAL
                    )
                ):
                    self._json = self.__parseJSON(self.__requestJSON())
                    self._last_update_check = datetime.datetime.now()

                    # sanity check
                    if not self._json:
                        temp_value = False

                    else:
                        if self._json["latest_version"] != self._submod.version:
                            temp_value = True

                        else:
                            temp_value = False

                    with self.__updateAvailablePropLock:
                        self._update_available = temp_value

                return temp_value

        def _checkUpdateInThread(bypass=False):
            """
            Runs _checkUpdate in a thread

            IN:
                bypass - whether or not we should try to bypass the limit
                    NOTE: DANGEROUS
                    (Default: False)
            """
            update_checker = threading.Thread(
                target=self._checkUpdate,
                kwargs=dict(bypass=bypass)
            )

            update_checker.start()

        def isUpdateAvailable(self, should_check=True):
            """
            Geneal way to check whether or not
            there's an update for this submod

            IN:
                should_check - whether we send a request to GitHub (True),
                    or return False if we don't have the update data (False)
                    (Default: True)

            OUT:
                True if there's an update,
                False otherwise
            """
            # Order of accessing these is important
            with self.__updatingPropLock:
                updating = self.__updating

            with self.__updatedPropLock:
                updated = self.__updated

            with self.__updateAvailablePropLock:
                update_available = self._update_available

            if (
                updated
                or updating
            ):
                return False

            if update_available is not None:
                return update_available

            if should_check:
                return self._checkUpdate()

            else:
                return False

        def _downloadUpdate(self, update_dir=None, extraction_depth=0, temp_folder_name=None):
            """
            Download the latest update for the submod
            NOTE: does not check for update
            NOTE: won't do anything if we're still updating another submod

            IN:
                update_dir - the directory the updater will extract this update into
                    NOTE: if None, the update will be installed in the submod directory
                    NOTE: if empty string, the update will be installed right in the game directory (the folder with DDLC.exe)
                    (Defaut: None)

                extraction_depth - the extraction depth, check the __extract_files method for explanation
                    (Default: 0)

                temp_folder_name - the name of the folder for keeping temp files for this update
                    NOTE: if None, the updater will generate one
                    (Default: None)

            OUT:
                True if we successfully downloaded and installed the update,
                False otherwise
            """
            # # # Define inner helper methods
            def __check_filepath(path):
                """
                Checks the given path and makes folders if needed
                """
                try:
                    if not os.path.isdir(path):
                        os.makedirs(path)

                except Exception as e:
                    self.__writeLog("Failed to check/create folders.", e)

            def __extract_files(curr_path, new_path, depth=0):
                """
                A helper method to extract files from one folder into another
                using the given depth to extract items from

                For example:
                    File in '/old_folder/sub_folder/file'
                    - with the depth 0 would be extracted as '/new_folder/sub_folder/file'
                    - with the depth 1 (and more in this case) would be extracted as '/new_folder/file'

                if the extracting object is a file, it would be moved to the destination
                regardless of the depth used

                NOTE: new_path can't end up inside curr_path
                NOTE: unsafe: no checks, nor try/except blocks

                IN:
                    curr_path - the folder which we'll extract files from
                    new_path - the destination
                    depth - the depth of recursion
                """
                if os.path.isdir(curr_path):
                    for item in os.listdir(curr_path):
                        if depth > 0:
                            _curr_path = curr_path + "/" + item
                            _depth = depth - 1

                            __extract_files(_curr_path, new_path, _depth)

                        else:
                            _curr_path = curr_path + "/" + item
                            _new_path = new_path + "/" + item

                            if os.path.exists(_new_path):
                                if os.path.isfile(_new_path):
                                    os.remove(_new_path)

                                else:
                                    removeFolders(_new_path, ignore_errors=True)

                            os.rename(_curr_path, _new_path)

                else:
                    _new_path = new_path + "/" + curr_path.rpartition("/")[-1]

                    if os.path.exists(_new_path):
                        if os.path.isfile(_new_path):
                            os.remove(_new_path)

                        else:
                            removeFolders(_new_path, ignore_errors=True)

                    os.rename(curr_path, _new_path)

            def __delete_update_files(*paths):
                """
                Tries to delete files in path
                NOTE: no exceptions/no logs

                IN:
                    paths - paths to files
                """
                for path in paths:
                    try:
                        if os.path.isdir(path):
                            removeFolders(path, ignore_errors=True)

                        elif os.path.isfile(path):
                            os.remove(path)
                    except:
                        pass
            # # # End of helper methods defination

            # only allow one update at a time 
            with self.updateDownloadLock:
                with self.__updatingPropLock:
                    self.__updating = True

                # # # Sanity checks
                with self.__updatedPropLock:
                    updated = self.__updated

                with self.__updateAvailablePropLock:
                    update_available = self._update_available

                if (
                    updated
                    or not update_available
                ):
                    self.__writeLog("Aborting update. No new updates for '{0}' found.".format(self.id))

                    with self.__updatingPropLock:
                        self.__updating = False

                    return False

                if (
                    self._json is None
                    or self._json["update_package_url"] is None
                ):
                    self.__writeLog("Failed to update. Missing update JSON data.")

                    with self.__updatingPropLock:
                        self.__updating = False

                    return False

                # # # Set the paths
                if temp_folder_name is None:
                    temp_folder_name = "temp_{0}_{1}".format(
                        re.sub(self.FOLDER_NAME_PATTERN, "_", self.id).lower(),
                        int(time.time())
                    )

                if update_dir is None:
                    if not self._submod_dir:
                        self.__writeLog("Failed to update. Couldn't locate the submod directory for update.")

                        with self.__updatingPropLock:
                            self.__updating = False

                        return False

                    update_dir = self._submod_dir

                # make it an absolute path if needed
                if self.GAME_FOLDER not in update_dir:
                    if update_dir:
                        update_dir = "{0}{1}{2}".format(
                            self.GAME_FOLDER,
                            "/",
                            update_dir
                        )

                    else:
                        update_dir = self.GAME_FOLDER

                path_to_temp_files = "{0}{1}{2}{3}{4}".format(
                    self.GAME_FOLDER,
                    "/",
                    self._submod_dir,
                    "/",
                    temp_folder_name
                )
                temp_file_name = "update.zip"
                temp_file = "{0}{1}{2}".format(
                    path_to_temp_files,
                    "/",
                    temp_file_name
                )

                # # # Check the paths
                __check_filepath(path_to_temp_files)
                __check_filepath(update_dir)

                update_url = self._json["update_package_url"]
                update_request = urllib2.Request(
                    url=update_url,
                    headers=self.HEADERS
                )

                # # # Get update size
                try:
                    update_size = int(
                        urllib2.urlopen(update_request, timeout=15).info().getheaders("Content-Length")[0]
                    )

                except Exception as e:
                    self.__writeLog("Failed to update. Failed to request update size.", e)

                    with self.__updatingPropLock:
                        self.__updating = False

                    return False

                # # # Prep for updating
                bytes_downloaded = 0
                bottom_bracket = 0
                top_bracket = self.REQUEST_CHUNK
                temp_headers = dict(self.HEADERS)
                temp_headers.update(
                    {
                        "Range": "bytes={0}-{1}".format(
                            bottom_bracket,
                            top_bracket
                        )
                    }
                )

                update_request = urllib2.Request(url=update_url, headers=temp_headers)

                # # # Start updating
                try:
                    with open(temp_file, "wb") as update_file:
                        response = urllib2.urlopen(update_request, timeout=15)
                        while True:
                            cache_buffer = response.read(self.WRITING_CHUNK)

                            if not cache_buffer:
                                break

                            bytes_downloaded += len(cache_buffer)
                            update_file.write(cache_buffer)

                            if (
                                bytes_downloaded == top_bracket
                                and not bytes_downloaded == update_size
                            ):
                                bottom_bracket = top_bracket
                                top_bracket += self.REQUEST_CHUNK
                                temp_headers["Range"] = "bytes={0}-{1}".format(bottom_bracket, top_bracket)
                                update_request = urllib2.Request(url=update_url, headers=temp_headers)
                                response = urllib2.urlopen(update_request, timeout=15)

                except Exception as e:
                    self.__writeLog("Failed to download update.", e)
                    __delete_update_files(path_to_temp_files)

                    if self.__raise_critical:
                        raise SubmodError(
                            "\n  Failed to download update. You may need to manually delete this folder and all files inside:\n    \"{0}\"".format(
                                path_to_temp_files
                            )
                        )

                    with self.__updatingPropLock:
                        self.__updating = False

                    return False

                try:
                    # unzip :S
                    with ZipFile(temp_file, "r") as update_file:
                        update_file.extractall(path_to_temp_files)

                except Exception as e:
                    self.__writeLog("Failed to extract update.", e)
                    __delete_update_files(path_to_temp_files)

                    if self.__raise_critical:
                        raise SubmodError(
                            "\n  Failed to extract update. You may need to manually delete this folder and all files inside:\n    \"{0}\"".format(
                                path_to_temp_files
                            )
                        )

                    with self.__updatingPropLock:
                        self.__updating = False

                    return False

                # delete update.zip
                try:
                    os.remove(temp_file)

                except Exception as e:
                    # this's not so bad, we can continue updating
                    self.__writeLog("Failed to delete temp files.", e)

                # move the files
                try:
                    __extract_files(path_to_temp_files, update_dir, extraction_depth)

                except Exception as e:
                    self.__writeLog("Failed to move update files.", e)
                    __delete_update_files(path_to_temp_files, update_dir)

                    if self.__raise_critical:
                        raise SubmodError(
                            (
                                "\n  Failed to move update files. You may need to manually delete these folders and all files inside:"
                                "\n    \"{0}\""
                                "\n    \"{1}\""
                                "\n  After that you'll need to reinstall the \"{2}\" v{3} submod."
                            ).format(
                                path_to_temp_files,
                                update_dir,
                                self.id,
                                self._json["latest_version"]
                            )
                        )

                    with self.__updatingPropLock:
                        self.__updating = False

                    return False

                # delete temp folders
                try:
                    removeFolders(path_to_temp_files, ignore_errors=True)

                except Exception as e:
                    # this's not so bad, we can finish updating
                    self.__writeLog("Failed to remove temp folders.", e)

                self.__writeLog(
                    "Downloaded and installed the {0} update for '{1}'.".format(
                        self._json["latest_version"],
                        self.id
                    ),
                    is_error=False
                )

                with self.__updatingPropLock:
                    self.__updating = False

                with self.__updatedPropLock:
                    self.__updated = True

                return True

        def downloadUpdateInThread(self, update_dir=None, extraction_depth=0, temp_folder_name=None):
            """
            Download the latest update for the submod using threading
            (basically runs _downloadUpdate in a thread)
            NOTE: does not check for update
            NOTE: won't do anything if we're still updating another submod

            IN:
                update_dir - the directory the updater will extract this update into
                    NOTE: if None, the update will be installed in the submod directory
                    NOTE: if empty string, the update will be installed right in the game directory (with DDLC.exe)
                    (Defaut: None)

                extraction_depth - the extraction depth, check the main method for explanation
                    (Default: 0)

                temp_folder_name - the name of the folder for keeping temp files for this update
                    NOTE: if None, the updater will generate one
                    (Default: None)
            """
            downloader = threading.Thread(
                target=self._downloadUpdate,
                kwargs=dict(update_dir=update_dir, extraction_depth=extraction_depth, temp_folder_name=temp_folder_name)
            )

            downloader.start()

        @classmethod
        def getUpdater(cls, name):
            """
            Gets an updater from the map

            IN:
                name - name of the updater

            OUR:
                SubmodUpdater object, or None if not found.
            """
            return cls.registered_updaters.get(name, None)

        @classmethod
        def _isUpdatingAny(cls):
            """
            Checks if we're updating a submod right now

            OUT:
                True if have an ongoing update,
                False otherwise
            """
            for updater in cls.registered_updaters.itervalues():
                with updater.__updatingPropLock:
                    if updater.__updating:
                        return True

            return False

        @classmethod
        def hasUpdateFor(cls, submod_name, should_check=True):
            """
            Checks if there's an update for a submod
            (basically checks isUpdateAvailable)

            IN:
                submod_name - name of the submod to check
                should_check - whether we send a request to GitHub (True),
                    or return False if we don't have the update data (False)
                    (Default: True)

            OUT:
                True if there's an update,
                False if no updates, or the submod doesn't exist
            """
            updater = cls.getUpdater(submod_name)
            if updater is not None:
                return updater.isUpdateAvailable(should_check=should_check)

            return False

        @classmethod
        def _notify(cls):
            """
            Notifies the user about all available submods
            NOTE: does not check for updates
            """
            additional_lines = list()

            for updater in cls.registered_updaters.itervalues():
                if (
                    updater.should_notify
                    and updater.isUpdateAvailable(should_check=False)
                ):
                    additional_lines.append(
                        "\n    '{0}'  {1}  >>>  {2}  ".format(
                            updater._submod.name,
                            updater._submod.version,
                            updater.latest_version
                        )
                    )

            # one line per submod
            total = len(additional_lines)

            if total > 1:
                main_line = "There're submod updates available:  {}"

            elif total == 1:
                main_line = "There's a submod update available:  {}"

            # nothing to notify about
            else:
                return

            notify_message = main_line.format(
                "".join(additional_lines)
            )
            renpy.notify(notify_message)

        @classmethod
        def _checkUpdates(cls):
            """
            Check updates for each registered submods
            """
            for updater in cls.registered_updaters.itervalues():
                if updater.auto_check:
                    updater._checkUpdate()

        @classmethod
        def _doLogic(cls, check_updates=True, notify=True):
            """
            Checks each submod for available updates
            and notifies the user if needed

            IN:
                check_updates - whether or not we check for updates
                notify - whether or not we show the notification
            """
            if check_updates:
                cls._checkUpdates()
            if notify:
                cls._notify()

        @classmethod
        def doLogicInThread(cls, check_updates=True, notify=True):
            """
            Runs doLogic in a thread

            IN:
                check_updates - whether or not we check for updates
                notify - whether or not we show the notification
            """
            checker = threading.Thread(
                target=cls._doLogic,
                args=(check_updates, notify)
            )

            checker.start()

        @classmethod
        def getUpdatersForOutdatedSubmods(cls):
            """
            Returns updater object for each outdated submod
            NOTE: does not check for updates itself

            OUT:
                list of updaters
            """
            return [
                updater
                for updater in cls.registered_updaters.itervalues()
                if updater.isUpdateAvailable(should_check=False)
            ]

        @classmethod
        def hasOutdatedSubmods(cls):
            """
            Returns a boolean whether or not the user has otudated submods
            NOTE: does not check for updates itself

            OUT:
                True if has, False if has not
            """
            return bool(len(cls.getUpdatersForOutdatedSubmods()) > 0)

        @classmethod
        def getIcon(cls, submod_name):
            """
            Returns an appropriate image for different update states
            TODO: consider using condition switch

            IN:
                submod_name - name of the submod to get img for

            OUT:
                the img name as a string,
                or None if no appropriate img found
            """
            img = None
            updater = cls.getUpdater(submod_name)

            if updater is not None:
                with updater.__updatingPropLock:
                    updating = updater.__updating

                with updater.__updatedPropLock:
                    updated = updater.__updated

                with updater.__updateAvailablePropLock:
                    update_available = updater._update_available

                # updating has priority
                if updating:
                    img = "sup_indicator_update_downloading"

                elif (
                    update_available
                    and not updated
                ):
                    img = "sup_indicator_update_available"

            return img

        @staticmethod
        def __writeLog(msg, e=None, is_error=True):
            """
            Writes exceptions in logs

            IN:
                msg - the message to write
                e - the exception to log
                    (Default: None)
            """
            error = " ERROR" if is_error else " REPORT"
            if e is None:
                _text = "[SUBMOD UPDATER PLUGIN{0}]: {1}\n".format(error, msg)

            else:
                _text = "[SUBMOD UPDATER PLUGIN{0}]: {1} Exception: {2}\n".format(error, msg, e)

            mas_utils.writelog(_text)

        @staticmethod
        def openURL(url):
            """
            Tries to open a url in the default browser
            Won't raise exceptions.

            IN:
                url - url to open

            OUT:
                True if we were able to open the url,
                False otherwise
            """
            if not url:
                return False

            try:
                openBrowser(url, new=2, autoraise=True)
                return True

            except:
                return False

        @staticmethod
        def openFolder(path):
            """
            Tried to open a folder in the default file manager
            Won't rise exceptions.

            IN:
                path - absolute path to open

            OUT:
                True if we were able to open the folder,
                False otherwise
            """
            # sanity check so you do not fook up
            # trying to do something illegal here
            if not os.path.isdir(path):
                return False

            path = path.replace("/", "\\")

            try:
                if renpy.windows:
                    subprocOpen(["explorer", path])
                    return True

                elif renpy.linux:
                    subprocOpen(["xdg-open", path])
                    return True

                elif renpy.macintosh:
                    subprocOpen(["open", path])
                    return True

                return False

            except:
                return False

# # # END OF SUBMODUPDATER CLASS

# # # Icons for different update states
image sup_indicator_update_downloading:
    "/Submods/Submod Updater Plugin/indicator_update_downloading.png"
    align (0.5, 0.5)
    alpha 0.0
    zoom 1.1
    subpixel True
    block:
        ease 0.75 alpha 1.0
        ease 0.75 alpha 0.1
        repeat

image sup_indicator_update_available:
    "/Submods/Submod Updater Plugin/indicator_update_available.png"
    align (0.5, 0.5)
    alpha 0.0
    zoom 1.2
    subpixel True
    block:
        ease 0.75 alpha 1.0
        ease 0.75 alpha 0.1
        repeat

# # # Confirm screen
#
# IN:
#    message - the message to display
#    yes_action - the action to do when the user presses the `Yes` button
#       (Default: NullAction)
#    no_action - the action to do when the user presses the `No` button
#       (Default: Hide("sup_confirm_screen"))
#
screen sup_confirm_screen(message, yes_action=NullAction(), no_action=Hide("sup_confirm_screen")):
    modal True

    zorder 200

    style_prefix "confirm"
    add mas_getTimeFile("gui/overlay/confirm.png")

    frame:
        vbox:
            align (0.5, 0.5)
            spacing 30

            label message:
                style "confirm_prompt"
                xalign 0.5

            hbox:
                xalign 0.5
                spacing 100

                textbutton "Yes":
                    action yes_action
                textbutton "No":
                    action no_action

# # # Submod screen
screen sup_setting_pane():
    python:
        def __getScrollBarHeight(items):
            """
            Calcualtes height for the scrollbar
            (from 33 to 99 pxs)

            IN:
                items - viewpoint items

            OUT:
                int
            """
            total_items = len(items)
            limit = 99
            height = total_items * 33
            return height if height <= limit else limit

    # vars for all other submods
    default has_outdated_submods = store.sup_utils.SubmodUpdater.hasOutdatedSubmods()
    default updaters = store.sup_utils.SubmodUpdater.getUpdatersForOutdatedSubmods()
    default new_updates_text = "New updates found:" if len(updaters) > 1 else "A new update found:"

    # vars for this submods
    default sup_updater = store.sup_utils.SubmodUpdater.getUpdater("Submod Updater Plugin")
    default update_icon = store.sup_utils.SubmodUpdater.getIcon("Submod Updater Plugin")
    default vbox_ypos = -20 if update_icon is not None else 0

    # NOTE: here we place the icon near the title
    add update_icon:
        pos (325, -102)

    vbox:
        # NOTE: the icon takes about 20 px of place, so we move everything below it up to that height
        ypos vbox_ypos
        xmaximum 800
        xfill True
        yfill False
        style_prefix "check"

        if (
            sup_updater
            and store.sup_utils.SubmodUpdater.hasUpdateFor("Submod Updater Plugin", should_check=False)
            and not store.sup_utils.SubmodUpdater._isUpdatingAny()
        ):
            # textbutton "Update Submod Updater Plugin":
            #     pos (-24, 1)
            #     action ShowTransient("sup_confirm_screen", message="This will open a new tab in your browser.", yes_action=Function(store.sup_utils.SubmodUpdater.openURL, sup_updater.update_page_url))
            textbutton "Update Submod Updater Plugin":
                pos (-24, 1)
                action ShowTransient("sup_confirm_screen", message="Start updating Submod Updater Plugin v{0} to v{1}?".format(sup_updater._submod.version, sup_updater.latest_version), yes_action=Function(sup_updater.downloadUpdateInThread))

        if has_outdated_submods:
            vbox:
                xmaximum 800
                xfill True
                yfill False

                text "[new_updates_text]"

                hbox:
                    box_reverse True
                    viewport:
                        id "viewport"
                        ymaximum 99
                        xmaximum 780
                        xfill True
                        yfill False
                        mousewheel True

                        vbox:
                            xmaximum 780
                            xfill True
                            yfill False
                            box_wrap False

                            for updater in updaters:
                                hbox:
                                    xpos 20
                                    spacing 20
                                    xmaximum 780

                                    text "[updater._submod.name]"
                                    text "v[updater._submod.version]"
                                    text ">>>"
                                    text "v[updater.latest_version]"

                    bar:
                        style "classroom_vscrollbar"
                        xalign 0.005
                        ymaximum __getScrollBarHeight(updaters)
                        yfill False
                        value YScrollValue("viewport")
