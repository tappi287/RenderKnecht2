import re
from lxml import etree as Et


class FakomPattern:
    # FaKom pattern list
    pattern = list()

    # FaKom Pattern as tuple
    # (RegEx, Seat-Code-Index-Start, Seat-Code-Index-End, Color-index-start, Color-index-end)
    # (str, int, int, int[optional], int[optional])

    # FA_SIB_on
    pattern.append(('^.._..._on$', 0, 2, 3, 6))

    # FA_SIB_LUM_on
    pattern.append(('^.._..._..._on$', 0, 2, 3, 6))

    # FA_on_SIB_on
    pattern.append(('^.._.._..._..$', 0, 2, -6, -3))

    # FA_on_LUM_on_SIB_on
    pattern.append(('^.._on_..._on_..._on$', 0, 2, -6, -3))

    # LUM_on_FA_on_SIB_on
    pattern.append(('^..._on_.._on_..._on$', -6, -3, -12, -10))

    # FA_SIB
    pattern.append(('^.._...$', 0, 2, 3, 6))

    # FA_SIB_XXX
    pattern.append(('^.._..._...$', 0, 2, 3, 6))

    # LUM_FA_SIB_on
    pattern.append(('^..._.._..._on$', -6, -3, -9, -7))

    @classmethod
    def next(cls):
        for reg_ex, position in cls.pattern:
            yield reg_ex, position

    @staticmethod
    def search(pattern, action_list_name):
        """ Returns (Color_Code:str, Seat_Code:str) or None """
        reg_ex_pattern, (fa_start, fa_end, sib_start, sib_end) = pattern

        # RegEx search
        result = re.search(reg_ex_pattern, action_list_name, flags=re.IGNORECASE)

        if result:
            # Extract Colortrim PR
            color_key = result.string[fa_start:fa_end]

            # Extract Seat PR
            sib_key = result.string[sib_start:sib_end]

            return color_key, sib_key