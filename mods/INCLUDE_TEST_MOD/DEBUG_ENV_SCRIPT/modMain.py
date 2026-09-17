# -*- coding: utf-8 -*-
from .QuModLibs.QuMod import *
from .Game import (
    RELOAD_MOD,
    INIT_RELOAD_TIME,
    RELOAD_ADDON,
    RELOAD_WORLD,
    RELOAD_SHADERS,
)
from .Config import DEBUG_CONFIG
from .StdoutCapture import SET_LOG_SENDER, STD_OUT_WRAPPER
import sys

lambda: "By Zero123"

REF = 0


stdout = sys.stdout
stderr = sys.stderr
stdoutWrapper = STD_OUT_WRAPPER(stdout, "stdout")
stderrWrapper = STD_OUT_WRAPPER(stderr, "stderr")


def REST_STDOUT():
    stdoutWrapper.flush()
    stderrWrapper.flush()
    sys.stdout = stdout
    sys.stderr = stderr


sys.stdout = stdoutWrapper
sys.stderr = stderrWrapper


@PRE_SERVER_LOADER_HOOK
def SERVER_INIT():
    global REF
    REF += 1

    def _DESTROY():
        global REF
        REF -= 1
        if REF != 0:
            IPCSystem.ON_SERVER_EXIT()
            return
        REST_STDOUT()
        IPCSystem.ON_SERVER_EXIT()

    from .QuModLibs.Systems.Loader.Server import LoaderSystem

    LoaderSystem.REG_DESTROY_CALL_FUNC(_DESTROY)
    from . import IPCSystem
    SET_LOG_SENDER(IPCSystem.SEND_LOG)
    IPCSystem.ON_SERVER_INIT()


def CLOnKeyPressInGame(args={}):
    if args["isDown"] != "0":
        return
    if args["screenName"] != "hud_screen" and not DEBUG_CONFIG.get(
        "reload_key_global", False
    ):
        return
    key = args["key"]
    if key == str(DEBUG_CONFIG.get("reload_key", "82")):
        RELOAD_MOD()
    elif key == str(DEBUG_CONFIG.get("reload_world_key", "")):
        RELOAD_WORLD()
    elif key == str(DEBUG_CONFIG.get("reload_addon_key", "")):
        RELOAD_ADDON()
    elif key == str(DEBUG_CONFIG.get("reload_shaders_key", "")):
        RELOAD_SHADERS()


@PRE_CLIENT_LOADER_HOOK
def CLIENT_INIT():
    global REF
    REF += 1
    from . import IPCSystem
    SET_LOG_SENDER(IPCSystem.SEND_LOG)

    def _DESTROY():
        global REF
        REF -= 1
        if REF != 0:
            IPCSystem.ON_CLIENT_EXIT()
            return
        REST_STDOUT()
        IPCSystem.ON_CLIENT_EXIT()

    from .QuModLibs.Systems.Loader.Client import LoaderSystem

    LoaderSystem.REG_DESTROY_CALL_FUNC(_DESTROY)

    LoaderSystem.getSystem().nativeStaticListen("OnKeyPressInGame", CLOnKeyPressInGame)
    IPCSystem.ON_CLIENT_INIT()


try:
    INIT_RELOAD_TIME()
except:
    pass
