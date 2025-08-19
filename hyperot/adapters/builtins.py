from . import replace_res, replace_common, replace_listener


def load_onebot():
    from hyperot.LecAdapters.OneBotLib import Res as OneBotRes

    replace_res(OneBotRes)

    from hyperot.LecAdapters.OneBotLib import Manager as OneBotCommon

    replace_common(OneBotCommon)

    from hyperot.LecAdapters import OneBot as OneBotListener

    replace_listener(OneBotListener)
