
# Register the submod
init -990 python in mas_submod_utils:
    Submod(
        author="Booplicate",
        name="Submod Updater Plugin",
        description=(
            "A util submod that makes updating other submods easier. "
            "More information on the project's {a=https://github.com/Booplicate/MAS-Submods-SubmodUpdaterPlugin}{i}{u}GitHub{/u}{/i}{/a}."
        ),
        version="1.0",
        settings_pane="sup_setting_pane"
    )

# Register the updater
init -980 python in sup_utils:
    SubmodUpdater(
        submod="Submod Updater Plugin",
        user_name="Booplicate",
        repository_name="MAS-Submods-SubmodUpdaterPlugin",
        update_dir=""
    )

# # # auto-update checks
init -970 python in sup_utils:
    mas_submod_utils.registerFunction("ch30_reset", SubmodUpdater.doLogicInThread, auto_error_handling=False)
    mas_submod_utils.registerFunction("ch30_day", SubmodUpdater.doLogicInThread, auto_error_handling=False)

# # # SUBMODUPDATER CLASS
init -981 python in sup_utils:
    import store.mas_submod_utils as mas_submod_utils
    import store.mas_utils as mas_utils
    import re
    import os
    import shutil
    import datetime
    import time
    import urllib2
    import threading
    from store import ConditionSwitch
    from json import loads as loadJSON
    from zipfile import ZipFile
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
                allow_updates - whether or not allow the user to install updtes for this submod
                submod_dir - the relative file path to the submod directory
                update_dir - directory where updates will be installed to
                extraction_depth - depth of the recursion for the update extractor
                json - json data about submod from GitHub
                last_update_check - datetime.datetime the last time we checked for update
                update_available - whether or not we have an update available

            private:
                user_name - the author's user name on GitHub
                repository_name - the submod's GitHub repository name
                attachment_id - id of the attachment on GitHub (usually 0)
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

        # number of attempts to requests content size
        # before aborting the update
        REQUEST_ATTEMPS_LIMIT = 10

        # IO file chunks
        REQUEST_CHUNK = 5242880
        WRITING_CHUNK = 262144

        # lock for threading stuff
        updateDownloadLock = threading.Lock()

        # Renpy can suck this bar - I have working progress bar for windows
        single_progress_bar = SUPProgressBar()
        bulk_progress_bar = SUPProgressBar()

        # normalized path of the game directory
        BASE_DIRECTORY = renpy.config.basedir.replace("\\", "/")

        FOLDER_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_]")

        # html codes
        OK_CODE = 200
        RATE_LIMIT_CODE = 403

        # a map of submods which we will check for updates
        registered_updaters = dict()

        # a list of updaters that were queued for updating
        queued_updaters = list()
        # a list of updaters resently finished updating
        finished_updaters = list()

        def __init__(
            self,
            submod,
            user_name,
            repository_name,
            should_notify=True,
            auto_check=True,
            allow_updates=True,
            submod_dir=None,
            update_dir=None,
            extraction_depth=1,
            attachment_id=0
        ):
            """
            Constructor

            IN:
                submod - either the name of the submod
                    or the Submod object itself

                user_name - the author's user name (login) on GitHub

                repository_name - the submod's GitHub repository name

                should_notify - whether or not we notify the user about updates
                    This includes both: showing notifies and showing update information on the submod screen
                    (Default: True)

                auto_check - whether or not we automically check for updates (this's not auto updating)
                    (Default: True)

                allow_updates - whether or not allow the user to install updtes for this submod
                    If True there wll be a button to prompt for the update in the submod screen
                    If False you'll need to implement another way to update (or don't if you only want to notify about updates)
                    (Default: True)

                submod_dir - relative file path to the directory of the submod
                    e.g. 'game/.../your submod folder'
                    NOTE: if None, the updater will try to find the path itself
                    NOTE: if None when we're trying to update the submod and no update_dir specified, the update will be aborted
                    (Default: None)

                update_dir - directory where updates will be installed to
                    NOTE: if None, updates will be installed in the submod directory if one was specified
                    NOTE: if empty string, updates will be installed right in the base directory (the folder with DDLC.exe)
                    (Default: None)

                extraction_depth - extraction depth, depth of the recursion for the update extractor
                    See the __extract_files method for more info
                    (Default: 1)

                attachment_id - id of the attachment on GitHub
                    (only if you have more than one attachment in releases, not counting source code)
                    NOTE: if set to None, the updater will download the source files
                        while it is supported by this util, it's not supported well by GitHub
                        better use an attachment
                    (Default: 0)
            """
            if isinstance(submod, basestring):
                submod_name = submod
                submod_obj = mas_submod_utils.submod_map.get(submod, None)

            elif isinstance(submod, mas_submod_utils.Submod):
                submod_name = submod.name
                submod_obj = submod

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
            self.allow_updates = allow_updates
            self._submod_dir = submod_dir or self.__getFilePath()
            self._update_dir = update_dir
            self._extraction_depth = extraction_depth
            self.__attachment_id = attachment_id

            self.__json_request = self.__buildJSONRequest()
            self._json = None
            self._last_update_check = None
            self._update_available = None
            self.__updated = False
            self.__updating = False

            self.__updateCheckLock = threading.Lock()
            # self.__updateAvailablePropLock = threading.Lock()
            # self.__updatingPropLock = threading.Lock()
            # self.__updatedPropLock = threading.Lock()

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

        def toggleUpdates(self):
            """
            Toggles the allow_updates property
            """
            self.allow_updates = not self.allow_updates

        def isUpdating(self):
            """
            Returns a bool whether we're updating this submod now
            """
            return self.__updating

        def hasUpdated(self):
            """
            Returns a bool whether we updated this submod
            """
            return self.__updated

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

        def getDirectory(self, absolute=True):
            """
            Returns the submod directory

            IN:
                absolute - True to return the absolute path,
                    False to return the relative one

            OUT:
                string with the path, or None if we couldn't find it
            """
            path = None
            if self._submod_dir is not None:
                if absolute:
                    path = os.path.join(self.BASE_DIRECTORY, self._submod_dir).replace("\\", "/")

                else:
                    path = self._submod_dir

            return path

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
                    if (
                        self._json
                        and self._json["latest_version"] != self._submod.version
                    ):
                        self._update_available = True

                    else:
                        self._update_available = False

            return self._update_available

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

        def hasUpdate(self, should_check=True, ignore_if_updated=True, ignore_if_updating=True):
            """
            Geneal way to check if there's an update for this submod

            IN:
                should_check - whether we send a request to GitHub (True),
                    or return False if we don't have the update data (False)
                    (Default: True)

                ignore_if_updated - whether or not skip this check if the submod was updated
                    (Default: True)

                ignore_if_updating - whether or not skip this check if the submod is being updated now
                    (Default: True)

            OUT:
                True if there's an update,
                False otherwise
            """
            if (
                (
                    self.__updating
                    and ignore_if_updating
                )
                or (
                    self.__updated
                    and ignore_if_updated
                )
            ):
                return False

            if self._update_available is not None:
                return self._update_available

            if should_check:
                return self._checkUpdate()

            else:
                return False

        def _downloadUpdate(self, update_dir=None, extraction_depth=1):
            """
            Download the latest update for the submod
            NOTE: does not check for update
            NOTE: won't do anything if we're still updating another submod
            NOTE: For internal uses the arguments for this method the updater will take from the properties

            IN:
                update_dir - the directory the updater will extract this update into
                    NOTE: if None, the update will be installed in the submod directory
                    NOTE: if empty string, the update will be installed right in the base directory (the folder with DDLC.exe)
                    (Default: None)

                extraction_depth - extraction depth, check the __extract_files method for explanation
                    (Default: 1)

            OUT:
                True if we successfully downloaded and installed the update,
                False otherwise
            """
            # # # Define inner helper methods
            def __check_filepath(path):
                """
                Checks the given path and makes folders if needed

                IN:
                    path - path to check
                """
                try:
                    if not os.path.isdir(path):
                        os.makedirs(path)

                    return True

                except Exception as e:
                    self.__writeLog("Failed to check/create folders.", e)
                    return False

            def __extract_files(srs, dst, depth=0):
                """
                A helper method to extract files from one folder into another
                using the given depth to extract items from

                For example:
                    File in 'old_folder/sub_folder/file'
                    - with the depth 0 would be extracted as 'new_folder/sub_folder/file'
                    - with the depth 1 (and more in this case) would be extracted as 'new_folder/file'

                if the extracting object is a file, it would be moved to the destination
                regardless of the depth used

                NOTE: dst can't end up inside srs

                IN:
                    srs - the folder which we'll extract files from
                    new_path - the destination
                    depth - depth of the recursion

                OUT:
                    list of exceptions (it can be empty)
                """
                exceptions = []
                if os.path.isdir(srs):
                    for item in os.listdir(srs):
                        new_srs = os.path.join(srs, item).replace("\\", "/")
                        new_dst = os.path.join(dst, item).replace("\\", "/")
                        new_depth = depth - 1

                        if (
                            depth > 0
                            and os.path.isdir(new_srs)
                        ):
                            rv = __extract_files(new_srs, dst, new_depth)
                            exceptions += rv

                        else:
                            if os.path.isdir(new_dst):
                                rv = __extract_files(new_srs, new_dst, 0)
                                exceptions += rv

                            elif os.path.isfile(new_dst):
                                try:
                                    os.remove(new_dst)
                                    shutil.move(new_srs, dst)

                                except Exception as e:
                                    exceptions.append(str(e))

                            else:
                                try:
                                    shutil.move(new_srs, dst)

                                except Exception as e:
                                    exceptions.append(str(e))

                return exceptions

            def __delete_update_files(path):
                """
                Tries to delete files in path

                IN:
                    path - path to files
                """
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)

                    elif os.path.isfile(path):
                        os.remove(path)
                except Exception as e:
                    self.__writeLog("Failed to delete temp files: {0}".format(path), e)

            def __do_progress_bar_logic():
                """
                Does logic for updating the progress bar for bulk downloads
                """
                if self in self.queued_updaters:
                    self.finished_updaters.append(self)
                    bar_value = 1.0 / float(len(self.queued_updaters)) * 100
                    self.bulk_progress_bar.add_value(bar_value)

            # # # End of helper methods defination

            # only allow one update at a time 
            with self.updateDownloadLock:
                # Reset the previous state
                self.single_progress_bar.reset()
                self.__updating = True

                # # # Sanity checks
                if (
                    self.__updated
                    or not self._update_available
                ):
                    self.__writeLog("Aborting update. No new updates for '{0}' found.".format(self.id))

                    self.__updating = False

                    __do_progress_bar_logic()

                    return False

                if (
                    self._json is None
                    or self._json["update_package_url"] is None
                ):
                    self.__writeLog("Failed to update. Missing update JSON data.")

                    self.__updating = False

                    __do_progress_bar_logic()

                    return False

                # # # Set the paths

                # You decided to install the update into the base dir
                if update_dir == "":
                    update_dir = self.BASE_DIRECTORY

                else:
                    # If we don't know the folder yet, try to get the one where we have the submod in
                    if update_dir is None:
                        if not self._submod_dir:
                            self.__writeLog("Failed to update. Couldn't locate the submod directory.")

                            self.__updating = False

                            __do_progress_bar_logic()

                            return False

                        update_dir = self._submod_dir

                    # Make it an absolute path if needed
                    if self.BASE_DIRECTORY not in update_dir:
                        update_dir = os.path.join(self.BASE_DIRECTORY, update_dir).replace("\\", "/")

                # if temp_folder_name is None:
                temp_folder_name = "temp_{0}_{1}".format(
                    re.sub(self.FOLDER_NAME_PATTERN, "_", self.id).lower(),
                    int(time.time())
                )

                temp_files_dir = os.path.join(self.BASE_DIRECTORY, self._submod_dir, temp_folder_name).replace("\\", "/")

                temp_file_name = "update.zip"

                temp_file = os.path.join(temp_files_dir, temp_file_name).replace("\\", "/")

                # # # Check the paths
                path_1 = __check_filepath(temp_files_dir)
                path_2 = __check_filepath(update_dir)

                # abort if we weren't able to create the folders
                if not path_1 or not path_2:
                    self.__updating = False

                    __do_progress_bar_logic()

                    return False

                update_url = self._json["update_package_url"]

                req_size_headers = dict(self.HEADERS)
                req_size_headers.update({"Accept-Encoding": "identity"})

                req_size_request = urllib2.Request(
                    url=update_url,
                    headers=req_size_headers
                )

                request_attempts_left = self.REQUEST_ATTEMPS_LIMIT# I literally hate GitHub for not allowing me to get Content-Length
                update_size = None

                # # # Get update size
                try:
                    while (
                        update_size is None
                        and request_attempts_left > 0
                    ):
                        cont_length_list = urllib2.urlopen(req_size_request, timeout=15).info().getheaders("Content-Length")

                        if len(cont_length_list) > 0:
                            update_size = int(cont_length_list[0])

                        else:
                            request_attempts_left -= 1
                            req_size_request = urllib2.Request(
                                url=update_url,
                                headers=req_size_headers
                            )
                            time.sleep(2)

                    # I give 10 attempts, if we fail, we fail. Blame GitHub.
                    if update_size is None:
                        self.__writeLog("Github failed to return update size. Try again later.")

                        self.__updating = False

                        __do_progress_bar_logic()

                        return False

                except Exception as e:
                    self.__writeLog("Failed to update. Failed to request update size.", e)

                    self.__updating = False

                    __do_progress_bar_logic()

                    return False

                # # # Prep for updating
                bytes_downloaded = 0
                bottom_bracket = 0
                top_bracket = self.REQUEST_CHUNK
                downloading_headers = dict(self.HEADERS)
                downloading_headers.update(
                    {
                        "Range": "bytes={0}-{1}".format(
                            bottom_bracket,
                            top_bracket
                        )
                    }
                )
                update_request = urllib2.Request(
                    url=update_url,
                    headers=downloading_headers
                )

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

                            bar_value = float(len(cache_buffer)) / float(update_size) * 100
                            self.single_progress_bar.add_value(bar_value)
                            time.sleep(0.25)

                            if (
                                bytes_downloaded == top_bracket
                                and bytes_downloaded != update_size
                            ):
                                bottom_bracket = top_bracket
                                top_bracket += self.REQUEST_CHUNK
                                downloading_headers["Range"] = "bytes={0}-{1}".format(bottom_bracket, top_bracket)
                                update_request = urllib2.Request(url=update_url, headers=downloading_headers)
                                response = urllib2.urlopen(update_request, timeout=15)

                except Exception as e:
                    self.__writeLog("Failed to download update.", e)

                    __delete_update_files(temp_files_dir)

                    self.__updating = False

                    __do_progress_bar_logic()

                    return False

                try:
                    # unzip :S
                    with ZipFile(temp_file, "r") as update_file:
                        update_file.extractall(temp_files_dir)

                except Exception as e:
                    self.__writeLog("Failed to extract update.", e)

                    __delete_update_files(temp_files_dir)

                    self.__updating = False

                    __do_progress_bar_logic()

                    return False

                # delete update.zip
                # even if it fails, it's not so bad, we can continue updating
                __delete_update_files(temp_file)

                # move the files
                exceptions = __extract_files(temp_files_dir, update_dir, extraction_depth)

                # even if we fail here, it's too late to abort now
                # but we can log exceptions
                if exceptions:
                    self.__writeLog("Failed to move update files. Exceptions:\n" + "\n".join(exceptions))

                    # __delete_update_files(temp_files_dir)

                    # self.__updating = False

                    # return False

                # delete temp folders
                __delete_update_files(temp_files_dir)

                self.__writeLog(
                    "Downloaded and installed the {0} update for '{1}'.".format(
                        self._json["latest_version"],
                        self.id
                    ),
                    is_error=False
                )

                self.__updating = False
                self.__updated = True

                __do_progress_bar_logic()

                return True

            return False

        def downloadUpdateInThread(self, update_dir=None, extraction_depth=1):
            """
            Download the latest update for the submod using threading
            (basically runs _downloadUpdate in a thread)
            NOTE: does not check for update
            NOTE: won't do anything if we're still updating another submod
            NOTE: For internal uses the arguments for this method the updater will take from the properties

            IN:
                update_dir - the directory the updater will extract this update into
                    NOTE: if None, the update will be installed in the submod directory
                    NOTE: if empty string, the update will be installed right in the base directory (with DDLC.exe)
                    (Default: None)

                extraction_depth - the extraction depth, check the main method for explanation
                    (Default: 1)
            """
            downloader = threading.Thread(
                target=self._downloadUpdate,
                kwargs=dict(update_dir=update_dir, extraction_depth=extraction_depth)
            )

            downloader.start()

        def _checkConflicts(self):
            """
            Checks if some of other submods will have issues if we update this submod
            NOTE: doesn't actually forbid updating, only prompts the user

            OUT:
                list of tuples with conflicting submods
                    format: (submod name, max supported/required version of this submod)
            """
            def __parse_version(version):
                """
                Parses a string version number to list format
                INFO: This method was borrowed from the submod framework

                IN:
                    version - version string to parse

                OUT:
                    list - representing the parsed version number
                """
                return map(int, version.split('.'))

            conflicting_submods = []

            # we shouldn't get here if we don't have the version number
            if self.latest_version is None:
                return conflicting_submods

            for submod in mas_submod_utils.submod_map.itervalues():
                # so it doesn't check itself
                if submod is not self._submod:
                    # we can get by name since we know what we're looking for
                    minmax_version_tuple = submod.dependencies.get(self._submod.name, None)

                    if (
                        minmax_version_tuple is not None
                        and len(minmax_version_tuple) > 1
                    ):
                        max_version = minmax_version_tuple[1]

                        if max_version:
                            rv = mas_utils.compareVersionLists(
                                __parse_version(max_version),
                                __parse_version(self.latest_version)
                            )

                            # we should prompt the user that this one might cause issues
                            if rv < 0:
                                conflicting_submods.append((submod.name, self._submod.name, max_version))

            return conflicting_submods

        @classmethod
        def updateSubmods(cls, updaters):
            """
            Queue the given updaters for update
            NOTE: updates only one submod at a time
            NOTE: no guarantees which submod will be updated first
            NOTE: this will use the default submod params:
                update_dir and extraction_depth

            IN:
                updaters - list of updaters whose submods we'll update
            """
            # We should use the lock to modify the list
            with cls.updateDownloadLock:
                # Reset after the previous update
                cls.queued_updaters = []
                cls.finished_updaters = []
                cls.bulk_progress_bar.reset()

                for updater in updaters:
                    cls.queued_updaters.append(updater)
                    updater.downloadUpdateInThread(
                        update_dir=updater._update_dir,
                        extraction_depth=updater._extraction_depth
                    )

        @classmethod
        def totalQueuedUpdaters(cls):
            """
            Returns the number of queued updaters
            """
            return len(cls.queued_updaters)

        @classmethod
        def totalFinishedUpdaters(cls):
            """
            Returns the number of finished updaters
            """
            return len(cls.finished_updaters)

        @classmethod
        def isBulkUpdating(cls):
            """
            Returns whether or not we have an ongoing bulk update
            """
            # in the end they should have equal length
            return cls.totalFinishedUpdaters() < cls.totalQueuedUpdaters()

        @classmethod
        def getDirectoryFor(cls, submod_name, absolute=True):
            """
            Returns the file path to a submod directory

            IN:
                submod_name - the name of the submod
                absolute - True to return the absolute path,
                    False to return the relative one

            OUT:
                string with the path,
                or None if we couldn't find it or submod doesn't exist
            """
            updater = cls.getUpdater(submod_name)
            if updater:
                return updater.getDirectory(absolute=absolute)

            return None

        @classmethod
        def getUpdater(cls, submod_name):
            """
            Gets an updater from the map

            IN:
                submod_name - id of the updater

            OUR:
                SubmodUpdater object, or None if not found.
            """
            return cls.registered_updaters.get(submod_name, None)

        @classmethod
        def _getUpdaterForUpdatingSubmod(cls):
            """
            Returns the updater for the submod that is currently being updated

            OUT:
                SubmodUpdater object, or None if not found.
            """
            for updater in cls.registered_updaters.itervalues():
                if updater.__updating:
                    return updater

            return None

        @classmethod
        def isUpdatingAny(cls):
            """
            Checks if we're updating a submod right now

            OUT:
                True if have an ongoing update,
                False otherwise
            """
            return cls._getUpdaterForUpdatingSubmod() is not None

        @classmethod
        def hasUpdateFor(cls, submod_name, should_check=True):
            """
            Checks if there's an update for a submod
            (basically checks hasUpdate)

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
                return updater.hasUpdate(should_check=should_check)

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
                    and updater.hasUpdate(should_check=False)
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
        def getUpdatersForOutdatedSubmods(cls, ignore_if_updated=True, ignore_if_updating=False, ignore_if_cant_update=False):
            """
            Returns updater object for each outdated submod
            NOTE: does not check for updates itself

            IN:
                ignore_if_updated - if True we'll skip already updated submods
                    (Default: True)

                ignore_if_updating - if True we'll skip currently updating submods
                    (Default: False)

                ignore_if_cant_update - if True we'll skip submods that can't be updated in-game
                    (Default: False)

            OUT:
                list of updaters
            """
            return [
                updater
                for updater in cls.registered_updaters.itervalues()
                if (
                    updater.hasUpdate(
                        should_check=False,
                        ignore_if_updated=ignore_if_updated,
                        ignore_if_updating=ignore_if_updating
                    )
                    and (
                        updater.allow_updates
                        or not ignore_if_cant_update
                    )
                )
            ]

        @classmethod
        def hasOutdatedSubmods(cls, ignore_if_updated=True, ignore_if_updating=False, ignore_if_cant_update=False):
            """
            Returns a boolean whether or not the user has outdated submods
            NOTE: does not check for updates itself

            IN:
                ignore_if_updated - if True we'll skip already updated submods
                    (Default: True)

                ignore_if_updating - if True we'll skip currently updating submods
                    (Default: False)

                ignore_if_cant_update - if True we'll skip submods that can't be updated in-game
                    (Default: False)

            OUT:
                True if has, False if has not
            """
            return len(
                cls.getUpdatersForOutdatedSubmods(
                    ignore_if_updated=ignore_if_updated,
                    ignore_if_updating=ignore_if_updating,
                    ignore_if_cant_update=ignore_if_cant_update
                )
            ) > 0

        @classmethod
        def getIcon(cls, submod_name):
            """
            Returns ConditionSwitch image for different update states

            IN:
                submod_name - name of the submod to get img for

            OUT:
                ConditionSwitch,
                or None if submod doesn't exist
            """
            # sanity check
            if cls.getUpdater(submod_name) is None:
                return None

            general_str = "store.sup_utils.SubmodUpdater.getUpdater('{}')".format(submod_name)

            is_updating_condition = general_str + ".isUpdating()"
            updating_img = "sup_indicator_update_downloading"
            is_update_available_condition = general_str + ".hasUpdate(should_check=False)"
            has_update_img = "sup_indicator_update_available"
            always_true_condition = "True"
            place_holder = "sup_indicator_no_update"

            return ConditionSwitch(
                is_updating_condition,
                updating_img,
                is_update_available_condition,
                has_update_img,
                always_true_condition,
                place_holder
            )

        @staticmethod
        def __writeLog(msg, e=None, is_error=True):
            """
            Writes exceptions in logs

            IN:
                msg - the message to write
                e - the exception to log
                    (Default: None)
                is_error - whether or not this logs an error
                    (Default: True)
            """
            message_type = " ERROR" if is_error else " REPORT"
            if e is None:
                _text = "[SUBMOD UPDATER PLUGIN{0}]: {1}\n".format(message_type, msg)

            else:
                _text = "[SUBMOD UPDATER PLUGIN{0}]: {1} Exception: {2}\n".format(message_type, msg, e)

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

# # # END OF THE SUBMODUPDATER CLASS

# # # SUPPROGRESSBAR CLASS
# Early defination since we're using this in the SubmodUpdater class
init -990 python in sup_utils:
    from store import AnimatedValue

    class SUPProgressBar(AnimatedValue):
        """
        Subclass of AnimatedValue which is a subclass of the BarValue class
        Implements advanced animated bar
        TODO:
            subclass the Bar class, add a screen statement for it
        """
        def __init__(self, value=0, range=100, delay=0.25, old_value=None):
            if old_value is None:
                old_value = value

            self.value = value
            self.range = range
            self.delay = delay
            self.old_value = old_value
            self.start_time = None

            self.adjustment = None

        def replaces(self, other):
            return

        def add_value(self, value):
            if self.value + value > self.range:
                value = self.range - self.value

            elif self.value + value < 0:
                value = 0 - self.value

            if value == 0:
                return

            self.old_value = self.adjustment._value
            self.value += value
            self.start_time = None
            renpy.restart_interaction()

        def reset(self):
            self.value = 0
            self.old_value = 0
            self.start_time = None

# # # END OF THE SUPPROGRESSBAR CLASS

# # # Icons for different update states
image sup_indicator_update_downloading:
    store.sup_utils.SubmodUpdater.getDirectoryFor("Submod Updater Plugin", True) + "/indicator_update_downloading.png"
    align (0.5, 0.5)
    ypos 1
    # alpha 0.0
    zoom 1.1
    subpixel True
    # block:
    #     ease 0.75 alpha 1.0
    #     ease 0.75 alpha 0.1
    #     repeat

image sup_indicator_update_available:
    store.sup_utils.SubmodUpdater.getDirectoryFor("Submod Updater Plugin", True) + "/indicator_update_available.png"
    align (0.5, 0.5)
    # alpha 0.0
    zoom 1.2
    subpixel True
    # block:
    #     ease 0.75 alpha 1.0
    #     ease 0.75 alpha 0.1
    #     repeat

# basically a placeholder
image sup_indicator_no_update = Solid("#00000000", xsize=20, ysize=20)

# predefine these to save some performance
image sup_text_updating_1 = Text("Updating the submod   ", size=15)
image sup_text_updating_2 = Text("Updating the submod.  ", size=15)
image sup_text_updating_3 = Text("Updating the submod.. ", size=15)
image sup_text_updating_4 = Text("Updating the submod...", size=15)

image sup_progress_bar_text:
    xanchor 0
    subpixel True
    block:
        "sup_text_updating_1"
        pause 0.75
        "sup_text_updating_2"
        pause 0.75
        "sup_text_updating_3"
        pause 0.75
        "sup_text_updating_4"
        pause 0.75
        repeat

# # # Update preview screen
#
# IN:
#    title - update title
#    body - update changelog
#
screen sup_update_preview(title, body):
    key "noshift_T" action NullAction()
    key "noshift_t" action NullAction()
    key "noshift_M" action NullAction()
    key "noshift_m" action NullAction()
    key "noshift_P" action NullAction()
    key "noshift_p" action NullAction()
    key "noshift_E" action NullAction()
    key "noshift_e" action NullAction()

    modal True

    zorder 200

    style_prefix "confirm"
    add mas_getTimeFile("gui/overlay/confirm.png")

    frame:
        vbox:
            align (0.5, 0.5)
            spacing 30

            label title:
                style "confirm_prompt"
                xalign 0.5

            viewport:
                ymaximum 200
                xmaximum 800
                xfill False
                yfill False
                mousewheel True
                scrollbars "vertical"

                text body.replace("\n", "\n\n")

            textbutton "Close":
                xalign 0.5
                action Hide("sup_update_preview")

# # # Confirm screen
#
# IN:
#    submod_updater - updater
#
screen sup_confirm_single_update(submod_updater):
    key "noshift_T" action NullAction()
    key "noshift_t" action NullAction()
    key "noshift_M" action NullAction()
    key "noshift_m" action NullAction()
    key "noshift_P" action NullAction()
    key "noshift_p" action NullAction()
    key "noshift_E" action NullAction()
    key "noshift_e" action NullAction()

    default conflicts = submod_updater._checkConflicts()
    default total_conflicts = len(conflicts)

    modal True

    zorder 200

    style_prefix "confirm"
    add mas_getTimeFile("gui/overlay/confirm.png")

    frame:
        vbox:
            align (0.5, 0.5)
            spacing 30

            label "Start updating [submod_updater.id] v[submod_updater._submod.version] to v[submod_updater.latest_version]?":
                style "confirm_prompt"
                xalign 0.5

            if total_conflicts > 0:
                viewport:
                    ymaximum 200
                    xmaximum 800
                    xfill False
                    yfill False
                    mousewheel True
                    scrollbars "vertical"

                    vbox:
                        spacing 5

                        text "Warning:"

                        null height 5

                        for conflicting_submod, this_submod, max_version in conflicts:
                            text "    - [conflicting_submod] supports maximum v[max_version] of [this_submod]"

                        null height 5

                        if total_conflicts > 1:
                            text "Updating those submods to their newer versions might fix that issue."

                        else:
                            text "Updating that submod to its newer version might fix that issue."

            hbox:
                xalign 0.5
                spacing 100

                textbutton "Yes":
                    action [
                        Function(
                            submod_updater.downloadUpdateInThread,
                            update_dir=submod_updater._update_dir,
                            extraction_depth=submod_updater._extraction_depth
                        ),
                        Hide("sup_confirm_single_update"),
                        Show("sup_single_update_screen")
                    ]

                textbutton "No":
                    action Hide("sup_confirm_single_update")

# # # Confirm screen
#
# IN:
#    submod_updaters - updaters
#
screen sup_confirm_bulk_update(submod_updaters):
    key "noshift_T" action NullAction()
    key "noshift_t" action NullAction()
    key "noshift_M" action NullAction()
    key "noshift_m" action NullAction()
    key "noshift_P" action NullAction()
    key "noshift_p" action NullAction()
    key "noshift_E" action NullAction()
    key "noshift_e" action NullAction()

    default conflicts = [conflict for submod_updater in submod_updaters for conflict in submod_updater._checkConflicts()]
    default total_conflicts = len(conflicts)

    modal True

    zorder 200

    style_prefix "confirm"
    add mas_getTimeFile("gui/overlay/confirm.png")

    frame:
        vbox:
            align (0.5, 0.5)
            spacing 30

            label "Start updating {b}all{/b} installed submods that can be updated?":
                style "confirm_prompt"
                xalign 0.5

            if total_conflicts > 0:
                viewport:
                    ymaximum 200
                    xmaximum 800
                    xfill False
                    yfill False
                    mousewheel True
                    scrollbars "vertical"

                    vbox:
                        spacing 5

                        text "Warning:"

                        null height 5

                        for conflicting_submod, updating_submod, max_version in conflicts:
                            text "    - [conflicting_submod] supports maximum v[max_version] of [updating_submod]"

                        null height 5

                        if total_conflicts > 1:
                            text "Updating those submods to their newer versions might fix that issue."

                        else:
                            text "Updating that submod to its newer version might fix that issue."

            hbox:
                xalign 0.5
                spacing 100

                textbutton "Yes":
                    action [
                        Function(
                            store.sup_utils.SubmodUpdater.updateSubmods,
                            submod_updaters
                        ),
                        Hide("sup_confirm_bulk_update"),
                        Show("sup_bulk_update_screen")
                    ]

                textbutton "No":
                    action Hide("sup_confirm_bulk_update")

# # # Update screen for single submod
screen sup_single_update_screen():
    # for safety
    key "K_ESCAPE" action NullAction()
    key "alt_K_F4" action NullAction()
    key "noshift_T" action NullAction()
    key "noshift_t" action NullAction()
    key "noshift_M" action NullAction()
    key "noshift_m" action NullAction()
    key "noshift_P" action NullAction()
    key "noshift_p" action NullAction()
    key "noshift_E" action NullAction()
    key "noshift_e" action NullAction()
    # for usability
    key "K_RETURN" action If(
        (
            not store.sup_utils.SubmodUpdater.isUpdatingAny()
        ),
        true=Hide("sup_single_update_screen"),
        false=NullAction()
    )

    modal True

    zorder 200

    style_prefix "confirm"
    add mas_getTimeFile("gui/overlay/confirm.png")

    frame:
        vbox:
            align (0.5, 0.5)
            xsize 440
            spacing 10

            if store.sup_utils.SubmodUpdater.isUpdatingAny():
                bar:
                    xalign 0.5
                    xysize (400, 25)
                    value store.sup_utils.SubmodUpdater.single_progress_bar
                    left_bar Frame(store.sup_utils.SubmodUpdater.getDirectoryFor("Submod Updater Plugin", True) + "/left_bar.png", 2, 2)
                    right_bar Frame(store.sup_utils.SubmodUpdater.getDirectoryFor("Submod Updater Plugin", True) + "/right_bar.png", 2, 2)
                    right_gutter 1

                add "sup_progress_bar_text":
                    xalign 0.5
                    xoffset 5
                    ypos -35

            else:
                if store.sup_utils.SubmodUpdater.hasOutdatedSubmods():
                    text "Please restart Monika After Story when you have finished installing updates.":
                        xalign 0.5
                        text_align 0.5

                else:
                    text "Please restart Monika After Story.":
                        xalign 0.5
                        text_align 0.5

                    null height 15

            textbutton "Ok":
                xalign 0.5
                sensitive not store.sup_utils.SubmodUpdater.isUpdatingAny()
                action Hide("sup_single_update_screen")

    timer 0.5:
        repeat True
        action Function(renpy.restart_interaction)

# # # Update screen for bulk updating
screen sup_bulk_update_screen():
    # for safety
    key "K_ESCAPE" action NullAction()
    key "alt_K_F4" action NullAction()
    key "noshift_T" action NullAction()
    key "noshift_t" action NullAction()
    key "noshift_M" action NullAction()
    key "noshift_m" action NullAction()
    key "noshift_P" action NullAction()
    key "noshift_p" action NullAction()
    key "noshift_E" action NullAction()
    key "noshift_e" action NullAction()
    # for usability
    key "K_RETURN" action If(
        (
            not store.sup_utils.SubmodUpdater.isUpdatingAny()# TODO: potentially it should be safe to do only one of these checks
            and not store.sup_utils.SubmodUpdater.isBulkUpdating()# and doing only isBulkUpdating would save some performance
        ),
        true=Hide("sup_bulk_update_screen"),
        false=NullAction()
    )

    modal True

    zorder 200

    style_prefix "confirm"
    add mas_getTimeFile("gui/overlay/confirm.png")

    frame:
        vbox:
            align (0.5, 0.5)
            xsize 440
            spacing 10

            if (
                store.sup_utils.SubmodUpdater.isUpdatingAny()
                or store.sup_utils.SubmodUpdater.isBulkUpdating()
            ):
                # total prrogression
                bar:
                    xalign 0.5
                    xysize (400, 25)
                    value store.sup_utils.SubmodUpdater.bulk_progress_bar# This's handled inside SubmodUpdater
                    left_bar Frame(store.sup_utils.SubmodUpdater.getDirectoryFor("Submod Updater Plugin", True) + "/left_bar.png", 2, 2)
                    right_bar Frame(store.sup_utils.SubmodUpdater.getDirectoryFor("Submod Updater Plugin", True) + "/right_bar.png", 2, 2)
                    right_gutter 1

                text "Progress: [store.sup_utils.SubmodUpdater.totalFinishedUpdaters()] / [store.sup_utils.SubmodUpdater.totalQueuedUpdaters()]":
                    xalign 0.5
                    text_align 0.5
                    size 15
                    ypos -35

                # currently updating submod prrogression
                bar:
                    xalign 0.5
                    xysize (400, 25)
                    value store.sup_utils.SubmodUpdater.single_progress_bar# This's handled inside SubmodUpdater
                    left_bar Frame(store.sup_utils.SubmodUpdater.getDirectoryFor("Submod Updater Plugin", True) + "/left_bar.png", 2, 2)
                    right_bar Frame(store.sup_utils.SubmodUpdater.getDirectoryFor("Submod Updater Plugin", True) + "/right_bar.png", 2, 2)
                    right_gutter 1

                add "sup_progress_bar_text":
                    xalign 0.5
                    xoffset 5
                    ypos -35

            else:
                text "Please restart Monika After Story.":
                    xalign 0.5
                    text_align 0.5

                null height 83

            textbutton "Ok":
                xalign 0.5
                sensitive (
                    not store.sup_utils.SubmodUpdater.isUpdatingAny()
                    and not store.sup_utils.SubmodUpdater.isBulkUpdating()
                )
                action Hide("sup_bulk_update_screen")

    timer 0.5:
        repeat True
        action Function(renpy.restart_interaction)

# # # Submod screen
init python in sup_utils:
    # helper method for this screen
    def _getScrollBarHeight(items):
        """
        Calcualtes height for the scrollbar
        (from 33 to 99 pxs)

        IN:
            items - viewpoint items

        OUT:
            int
        """
        height = 0
        limit = 140
        for item in items:
            height += 35

            if item.should_notify:
                height += 35

        return height if height <= limit else limit

screen sup_setting_pane():
    default submod_updaters = store.sup_utils.SubmodUpdater.getUpdatersForOutdatedSubmods()
    default total_submod_updaters = len(submod_updaters)
    default updatable_submod_updaters = store.sup_utils.SubmodUpdater.getUpdatersForOutdatedSubmods(ignore_if_cant_update=True)
    default total_updatable_submod_updaters = len(updatable_submod_updaters)
    default new_updates_found_text = "New updates found!" if total_submod_updaters > 1 else "A new update found!"

    vbox:
        ypos 0
        xmaximum 800
        xfill True
        yfill False
        style_prefix "check"

        if store.sup_utils.SubmodUpdater.hasOutdatedSubmods():
            vbox:
                xmaximum 800
                xfill True
                yfill False

                hbox:
                    spacing 0

                    text "[new_updates_found_text]"

                    if total_updatable_submod_updaters > 1:
                        textbutton "{b}Update all now!{/b}":
                            pos (-20, 1)
                            action ShowTransient("sup_confirm_bulk_update", submod_updaters=updatable_submod_updaters)

                    elif (
                        total_updatable_submod_updaters > 0
                        and total_submod_updaters > 2
                    ):
                        textbutton "{b}Update all now!{/b}":
                            pos (-20, 1)
                            action ShowTransient("sup_confirm_bulk_update", submod_updaters=[updatable_submod_updaters])

                hbox:
                    box_reverse True
                    viewport:
                        id "viewport"
                        ymaximum 140
                        xmaximum 780
                        xfill True
                        yfill False
                        mousewheel True

                        vbox:
                            xmaximum 780
                            xfill True
                            yfill False
                            box_wrap False

                            for submod_updater in submod_updaters:
                                if submod_updater.should_notify:
                                    hbox:
                                        xpos 20
                                        spacing 10
                                        xmaximum 780

                                        text "[submod_updater.id]"
                                        text "v[submod_updater._submod.version]"
                                        text " >>> "
                                        text "v[submod_updater.latest_version]"

                                    hbox:
                                        xpos 25
                                        spacing 10
                                        xmaximum 780

                                        textbutton "What's new?":
                                            ypos 1
                                            action ShowTransient(
                                                "sup_update_preview",
                                                title=submod_updater.update_name,
                                                body=submod_updater.update_changelog
                                            )

                                        if (
                                            submod_updater.allow_updates
                                            and not submod_updater.isUpdating()
                                        ):
                                            textbutton "Update now!":
                                                ypos 1
                                                action ShowTransient("sup_confirm_single_update", submod_updater=submod_updater)

                    bar:
                        style "classroom_vscrollbar"
                        xalign 0.005
                        ymaximum store.sup_utils._getScrollBarHeight(submod_updaters)
                        yfill False
                        value YScrollValue("viewport")

# # # Overrides
init 100:
    screen submods():
        tag menu

        use game_menu(("Submods")):

            default tooltip = Tooltip("")

            viewport id "scrollme":
                scrollbars "vertical"
                mousewheel True
                draggable True

                vbox:
                    style_prefix "check"
                    xfill True
                    xmaximum 1000

                    for submod in sorted(store.mas_submod_utils.submod_map.values(), key=lambda x: x.name):
                        vbox:
                            xfill True
                            xmaximum 1000

                            hbox:
                                spacing 10
                                xmaximum 1000

                                label submod.name yanchor 0 xalign 0

                                add store.sup_utils.SubmodUpdater.getIcon(submod.name):
                                    yanchor 0
                                    ypos 18

                            hbox:
                                spacing 20
                                xmaximum 1000

                                text "v{}".format(submod.version) yanchor 0 xalign 0 style "main_menu_version"
                                text "by {}".format(submod.author) yanchor 0 xalign 0 style "main_menu_version"

                            if submod.description:
                                text submod.description

                        if submod.settings_pane:
                            $ renpy.display.screen.use_screen(submod.settings_pane, _name="{0}_{1}".format(submod.author, submod.name))

        text tooltip.value:
            xalign 0 yalign 1.0
            xoffset 300 yoffset -10
            style "main_menu_version"
