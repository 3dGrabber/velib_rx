
DBUS_NONE = 'ai', []


def convert_python_value_to_dbus(value):
    # sorted (desc) according to presumed freq

    if isinstance(value, float):
        return 'd', value

    if isinstance(value, int):
        if -2147483648 <= value <= 2147483647:
            return 'i', value
        else:
            return 'x', value

    if isinstance(value, str):
        return 's', value

    if value is None:
        return DBUS_NONE

    if isinstance(value, bool):
        return 'b', value

    if isinstance(value, list):
        # always return an array of variants
        # lists in python can have mixed element types
        return 'av', [convert_python_value_to_dbus(e) for e in value]

    # TODO
    # if isinstance(value, dict):
    #     # Wrapping the keys of the dictionary causes D-Bus errors like:
    #     # 'arguments to dbus_message_iter_open_container() were incorrect,
    #     # assertion "(type == DBUS_TYPE_ARRAY && contained_signature &&
    #     # *contained_signature == DBUS_DICT_ENTRY_BEGIN_CHAR) || (contained_signature == NULL ||
    #     # _dbus_check_is_valid_signature (contained_signature))" failed in file ...'
    #     return dbus.Dictionary({(k, convert_python_value_to_dbus(v)) for k, v in value.items()}, variant_level=1)

    raise TypeError('unsupported python type')


