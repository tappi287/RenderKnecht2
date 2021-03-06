import re
from pathlib import Path
from typing import Union, List, Tuple, Set
from lxml import etree as Et


class FakomPattern:
    # FaKom pattern list
    pattern: List[Tuple[str, Tuple[int, int, int, int]]] = list()

    # FaKom Pattern as list of tuple(str, tuple(int, int, int, int))
    # (RegEx-String, (Color-index-start, Color-index-end, Seat-Code-Index-Start, Seat-Code-Index-End))
    fa = '[A-Z]{2}'      # match two letter color code
    sib = '[A-Z0-9]{3}'  # match three character alphanumeric PR code
    lum = '[A-Z0-9]{3}'  # match three character alphanumeric PR code

    # FA_SIB_on
    pattern.append((f'^{fa}_{sib}_on$', (0, 2, 3, 6)))

    # FA_SIB_LUM_on
    pattern.append((f'^{fa}_{sib}_{lum}_on$', (0, 2, 3, 6)))

    # FA_on_SIB_on
    pattern.append((f'^{fa}_on_{sib}_on$', (0, 2, -6, -3)))

    # FA_on_LUM_on_SIB_on
    pattern.append((f'^{fa}_on_{lum}_on_{sib}_on$', (0, 2, -6, -3)))

    # LUM_on_FA_on_SIB_on
    pattern.append((f'^{lum}_on_{fa}_on_{sib}_on$', (-12, -10, -6, -3)))

    # FA_SIB
    pattern.append((f'^{fa}_{sib}$', (0, 2, 3, 6)))

    # FA_SIB_XXX
    pattern.append((f'^{fa}_{sib}_{sib}$', (0, 2, 3, 6)))

    # LUM_FA_SIB_on
    pattern.append((f'^{lum}_{fa}_{sib}_on$', (-9, -7, -6, -3)))

    @classmethod
    def search(cls, action_list_name) -> Union[None, Tuple[str, str]]:
        """ Returns (Color_Code:str, Seat_Code:str) or None """
        for pattern in cls.pattern:
            reg_ex_pattern, (fa_start, fa_end, sib_start, sib_end) = pattern

            # RegEx search
            result = re.search(reg_ex_pattern, action_list_name, flags=re.IGNORECASE)

            if result:
                # Extract Colortrim PR
                color_key = result.string[fa_start:fa_end]

                # Extract Seat PR
                sib_key = result.string[sib_start:sib_end]

                return color_key, sib_key


class FakomData:
    def __init__(self):
        self._fakom_dict = dict()

    def add(self, color: str, sib: str):
        if color not in self._fakom_dict:
            self._fakom_dict[color] = set()

        self._fakom_dict[color].add(sib)

    def iterate_colors(self) -> Tuple[str, Set[str]]:
        for color, sib_set in self._fakom_dict.items():
            yield color, sib_set

    def empty(self) -> bool:
        if not self._fakom_dict:
            return True
        return False


class FakomReader:
    @staticmethod
    def iterate_action_lists(pos_file: Path) -> Tuple[str, str]:
        for _, al in Et.iterparse(pos_file.as_posix(), tag='actionList'):
            action_list_name = al.get('name') or ''

            result = FakomPattern.search(action_list_name)

            if not result:
                continue

            color, sib = result
            yield color, sib

    @classmethod
    def read_pos_file(cls, pos_file: Path):
        data = FakomData()

        for color, sib in cls.iterate_action_lists(pos_file):
            data.add(color, sib)

        return data
