import shutil
from pathlib import Path
from tempfile import mkdtemp
from time import time
from typing import List, Tuple, Union
from zipfile import ZIP_LZMA, ZipFile

import pandas as pd

from modules.globals import get_settings_dir
from modules.knecht_utils import list_class_fields, CreateZip
from modules.knecht_fakom import FakomData
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class _SheetColumns:
    """ Lists sheet columns indices or names """
    @classmethod
    def list(cls):
        return list_class_fields(cls)


class _Models:  # --- Models Worksheet ---
    name = 'models'  # Used for representation

    # Sheets containing this Type could be named:
    possible_sheet_names = ('Modelle', 'Models')
    # Sheets could contain empty columns with names:
    empty_columns = tuple()

    def __init__(self):
        # Used to locate columns independently of the column name
        class _ColumnIdx(_SheetColumns):
            """ Column locations """
            market = 0
            market_text = 1
            modelyear = 2
            model_class = 3
            model_class_text = 4
            derivate = 5
            model = 6
            version = 7
            status = 8
            model_text = 9
            start = 10
            end = 11
            engine_size = 12
            engine_power = 13
            gearbox = 14

        class _ColumnNames(_SheetColumns):
            market = 'Markt'
            market_text = 'Markttext'
            modelyear = 'Modelljahr'
            model_class = 'Klasse'
            model_class_text = 'Klassentext'
            derivate = 'Derivat'
            model = 'Modell'
            version = 'Version'
            status = 'Status'
            model_text = 'Modelltext'
            start = 'Einsatz'
            end = 'Entfall'
            engine_size = 'Hubraum'
            engine_power = 'Leistung'
            gearbox = 'Getriebe'

        self.ColumnIdx = _ColumnIdx()
        self.ColumnNames = _ColumnNames()


class _Pr:  # --- PR-Options Worksheet ---
    name = 'pr_options'

    possible_sheet_names = ('PR-Nummern', 'PR', 'Interior Scope', 'Exterior Scope',)
    empty_columns = ('Modell',)

    def __init__(self):
        class _ColumnIdx(_SheetColumns):
            """ Column locations """
            family = 0
            family_text = 1
            pr = 2
            pr_text = 3

        class _ColumnNames(_SheetColumns):
            family = 'PR-Familie'
            family_text = 'PR-FamilienText'
            pr = 'PR-Nummer'
            pr_text = 'Text'

        self.ColumnIdx = _ColumnIdx()
        self.ColumnNames = _ColumnNames()


class _Packages:  # --- Packages Worksheet ---
    name = 'packages'

    possible_sheet_names = ('Pakete', 'Pakete purged', 'Packages (purged)',)
    empty_columns = ('Modell',)

    def __init__(self):
        class _ColumnIdx(_SheetColumns):
            """ Column locations """
            package = 0
            package_text = 1
            pr = 2
            pr_text = 3

        class _ColumnNames(_SheetColumns):
            package = 'Paket'
            package_text = 'Pakettext'
            pr = 'PR-Nummer'
            pr_text = 'Text'

        self.ColumnIdx = _ColumnIdx()
        self.ColumnNames = _ColumnNames()


class ExcelMap:
    """ Definition where to obtain data in Excel sheets """
    def __init__(self):
        self.Models: _Models = _Models()
        self.Pr: _Pr = _Pr()
        self.Packages: _Packages = _Packages()

        # --- Define a Set of valid Worksheets to read ---
        # we will only accept worksheets with these known names
        self.valid_sheet_names = {
            *self.Models.possible_sheet_names,
            *self.Packages.possible_sheet_names,
            *self.Pr.possible_sheet_names,
            }

        # --- Required Sheet Types ---
        self.required_sheet_types = {self.Models, self.Pr}

    def update(self):
        self.valid_sheet_names = {
            *self.Models.possible_sheet_names, *self.Packages.possible_sheet_names, *self.Pr.possible_sheet_names,
            }
        self.required_sheet_types = {self.Models, self.Pr}


class Worksheet:
    def __init__(self,
                 name: str,
                 sheet_type: Union[None, _Models, _Pr, _Packages],
                 df: pd.DataFrame):
        """ Intermediate single worksheet """
        self.name, self.sheet_type, self.df = name, sheet_type, df


class ExcelData:
    file_names = ('pr.csv', 'pkg.csv', 'mdl.csv')

    def __init__(self, sheet_map: ExcelMap):
        """ Data extracted from one excel file as data frames """
        # Mutable ExcelMap Instance
        self.map = sheet_map

        # Dummy data
        self.pr_options, self.packages, self.models = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # Fakom data
        self.fakom = FakomData()

    def verify(self):
        if self.pr_options.empty or self.models.empty:
            return False
        return True

    def get_models(self) -> List[Tuple[str, str, str, str]]:
        """ Get list of tuples with model data: model code, market, description, gearbox """
        model_data = list()
        model_column = self.models.columns[self.map.Models.ColumnIdx.model]
        model_desc_column = self.models.columns[self.map.Models.ColumnIdx.model_text]
        market_column = self.models.columns[self.map.Models.ColumnIdx.market]
        gearbox_column = self.models.columns[self.map.Models.ColumnIdx.gearbox]

        for model in self.models[model_column]:
            model_rows = self.models.loc[self.models[model_column] == model]
            model_desc = model_rows[model_desc_column].unique()[0]
            market = model_rows[market_column].unique()[0]
            gearbox = model_rows[gearbox_column].unique()[0]

            model_data.append(
                (str(model), str(market), str(model_desc), str(gearbox))
                )

        return model_data

    def get_pr_families(self) -> List[Tuple[str, str]]:
        pr_family_data = list()
        family_column = self.pr_options.columns[self.map.Pr.ColumnIdx.family]
        family_text_column = self.pr_options.columns[self.map.Pr.ColumnIdx.family_text]

        for pr_family in self.pr_options[family_column].unique():
            pr_family_rows = self.pr_options.loc[self.pr_options[family_column] == pr_family]
            pr_family_desc = pr_family_rows[family_text_column].unique()[0]

            pr_family_data.append(
                (str(pr_family), str(pr_family_desc))
                )

        return pr_family_data

    def save_to_zip(self, file_path: Path=None) -> bool:
        if file_path is None:
            out_zip = Path(get_settings_dir()) / 'Excel_data.zip'
        else:
            out_zip = file_path

        tmp_dir = CreateZip.create_tmp_dir()

        for file_name, df in zip(self.file_names, (self.pr_options, self.packages, self.models)):
            csv_file = Path(tmp_dir) / file_name

            try:
                df.to_csv(csv_file.as_posix())
            except Exception as e:
                LOGGER.error(e)
                return False

        return CreateZip.save_dir_to_zip(tmp_dir, out_zip)

    def load_from_zip(self, file_path: Path=None) -> bool:
        if file_path is None:
            in_zip = Path(get_settings_dir()) / 'Excel_data.zip'

            if not in_zip.exists():
                return False
        else:
            in_zip = file_path

        try:
            with ZipFile(in_zip, 'r') as zip_file:
                for file_name, sheet_type in zip(self.file_names, (self.map.Pr, self.map.Packages, self.map.Models)):
                    with zip_file.open(file_name) as csv_file:
                        self._load_csv(csv_file, sheet_type)
        except Exception as e:
            LOGGER.error(e)
            return False

        return True

    def _load_csv(self, csv_file, sheet_type):
        df = pd.read_csv(csv_file, index_col=0)
        self.add_worksheet(Worksheet(csv_file.name, sheet_type, df))
        LOGGER.debug('Loaded dataframe with columns: %s', df.columns)

    def add_worksheet(self, worksheet: Worksheet):
        if worksheet.sheet_type == self.map.Pr:
            self.pr_options = worksheet.df
        elif worksheet.sheet_type == self.map.Packages:
            self.packages = worksheet.df
        elif worksheet.sheet_type == self.map.Models:
            self.models = worksheet.df

    def __add__(self, data: Union[Worksheet, List[Worksheet]]):
        if isinstance(data, list):
            for worksheet in data:
                self.add_worksheet(worksheet)
        elif isinstance(data, Worksheet):
            self.add_worksheet(data)

        return self


class ExcelReader:
    def __init__(self):
        """ Use read_file to parse an ExcelFile to an ExcelData object
            which is then accessible as ExcelReader.data
        """
        # --- ExcelMap definitions of this instance
        # Idea is to have a mutable Excel Mapping that can be adapted at runtime
        self.map = ExcelMap()

        # --- Error messages
        self.errors = list()

        # --- Store worksheets as data frames
        self.data = ExcelData(self.map)

    @staticmethod
    def _update_column_indices(df: pd.DataFrame, sheet_type: Union[_Pr, _Packages, _Models]):
        """ Lookup column indices and update self.map accordingly """
        for attribute_name, column_name in sheet_type.ColumnNames.list().items():
            if column_name in df.columns:
                column_index = df.columns.get_loc(column_name)
                setattr(sheet_type.ColumnIdx, attribute_name, column_index)
                LOGGER.debug('Mapping column: %s to index %s', column_name, column_index)

    def read_file(self, file: Path) -> bool:
        """ Read the excel file and return result

        :returns bool: True - successfully read file; False - read error, see errors
        """
        # Test file exists
        if not file.exists():
            self.errors.append(_('Datei exisitiert nicht: {}').format(file.as_posix()))
            LOGGER.error('Can not read file: %s', file.name)
            return False
        load_start = time()

        # Read to Pandas data frame
        with pd.ExcelFile(file.as_posix()) as excel_file:
            LOGGER.info('Parsing excel file: %s', file.name)

            worksheets = self._load_worksheets(excel_file)
            self.data += worksheets

            if not self._verify_loaded_worksheets(worksheets):
                return False

            if not self.data.verify():
                self.errors.append(_('Die Arbeitsblätter für PR-Optionen oder Modelle enthalten keine Daten '
                                     'oder konnten nicht gelesen werden.'))
                LOGGER.error('Dataframes for Worksheets PR-Options or Models are empty. Aborting Excel read.')
                return False

        LOGGER.info(f'Excel file parsed and converted to data frame in: {time() - load_start:.2f}s')
        return True

    def _load_worksheets(self, excel_file: pd.ExcelFile) -> List[Worksheet]:
        """ Collect required worksheets and return the result

        :returns bool: Found all required sheets True/False
        """
        LOGGER.debug('Loaded sheets: %s', excel_file.sheet_names)
        worksheets = list()
        pr_sheets = list()

        for name in excel_file.sheet_names:
            if name not in self.map.valid_sheet_names:
                LOGGER.info('Skipping unknown worksheet: %s', name)
                continue

            sheet = self._read_worksheet(excel_file, name)

            if sheet.sheet_type is self.map.Pr:
                pr_sheets.append(sheet)
            else:
                worksheets.append(sheet)

        if len(pr_sheets) > 1:
            # --- Concat multiple PR Data frames eg. Int/Ext to one data frame
            pr_dfs = [sheet.df for sheet in pr_sheets]
            pr_df = pd.concat(pr_dfs, sort=False)
            pr_sheet = Worksheet(self.map.Pr.possible_sheet_names[0], self.map.Pr, pr_df)
            worksheets.append(pr_sheet)
        else:
            worksheets += pr_sheets

        return worksheets

    def _read_worksheet(self, excel_file: pd.ExcelFile, name: str) -> Worksheet:
        """ Read all worksheets to DataFrame's create a worksheet list """
        sheet_type = None
        df = pd.DataFrame()

        if name in self.map.Pr.possible_sheet_names:
            LOGGER.info('Preparing PR worksheet: %s', name)
            sheet_type = self.map.Pr
            df = self._prepare_pr_dataframe(excel_file, name, sheet_type)
            df = self._prepare_pr_specific(df)
        elif name in self.map.Packages.possible_sheet_names:
            LOGGER.info('Preparing Package worksheet: %s', name)
            sheet_type = self.map.Packages
            df = self._prepare_pr_dataframe(excel_file, name, sheet_type)
            df = self._prepare_package_specific(df)
        elif name in self.map.Models.possible_sheet_names:
            LOGGER.info('Loading model worksheet: %s', name)
            df = excel_file.parse(name)
            sheet_type = self.map.Models

        self._update_column_indices(df, sheet_type)
        return Worksheet(name, sheet_type, df)

    def _prepare_pr_specific(self, df: pd.DataFrame) -> pd.DataFrame:
        """ Prepare part of the dataframe unique to PR Options sheet """
        # Forward fill PR-Family column and convert to category
        family_column = self.map.Pr.ColumnNames.family
        df[[family_column]] = df[[family_column]].ffill().astype('category')

        # Forward fill PR-Family Description column and convert to category
        family_text_column = self.map.Pr.ColumnNames.family_text
        df[[family_text_column]] = df[[family_text_column]].ffill().astype('category')

        df.dropna(subset=[self.map.Pr.ColumnNames.pr], inplace=True)

        return df

    def _prepare_package_specific(self, df: pd.DataFrame) -> pd.DataFrame:
        """ Prepare part of the dataframe unique to Packages sheet """
        # Forward fill Package column and convert to category
        package_column = self.map.Packages.ColumnNames.package
        df[[package_column]] = df[[package_column]].ffill().astype('category')

        # Forward fill Package Description column and convert to category
        package_text_column = self.map.Packages.ColumnNames.package_text
        df[[package_text_column]] = df[[package_text_column]].ffill().astype('category')

        df.dropna(subset=[self.map.Pr.ColumnNames.pr], inplace=True)

        return df

    @staticmethod
    def _prepare_pr_dataframe(excel_file: pd.ExcelFile, sheet_name: str,
                              sheet_type: Union[_Pr, _Packages]):
        """ Prepare the PR-Options or Package Worksheets.

            - parse with two-row header, mapping it back to one row and joining the model codes

              eg.   123
                    456
                    -> 123456

            - remove empty rows and columns
            - replace NaN with empty strings
        """

        def join_header_row_names(row_names: Tuple[str, str]):
            first_row, second_row = row_names

            if second_row.startswith('Unnamed'):
                return first_row
            else:
                return first_row + second_row

        # --- Parse Worksheet to DataFrame
        df = excel_file.parse(sheet_name,
                              skiprows=[0, 1],  # Skip first 2 empty rows
                              header=[0, 1]  # Define first 2 rows as header
                              )

        # --- Combine first 2 rows to one header row
        df.columns = df.columns.map(join_header_row_names)

        # --- Remove empty rows
        df.dropna(thresh=2, inplace=True)

        # --- Remove empty descriptive columns ---
        for empty_column in sheet_type.empty_columns:
            if empty_column in df.columns:
                df.drop(columns=[empty_column], inplace=True)

        return df

    def _verify_loaded_worksheets(self, worksheets: List[Worksheet]):
        """ Verify that at least one of each required Sheet Type has been found and loaded """
        loaded_sheet_types = set()
        for worksheet in worksheets:
            loaded_sheet_types.add(worksheet.sheet_type)

        missing_sheets = self.map.required_sheet_types.difference(loaded_sheet_types)

        if missing_sheets:
            self.errors.append(_('Es wurden nicht alle benötigten Arbeitsblätter gefunden '
                                 '{}. Es fehlen: {}').format([x.name for x in self.map.required_sheet_types],
                                                             [x.name for x in missing_sheets]))
            LOGGER.error('The excel file is missing the following required worksheets: %s',
                         [x.name for x in missing_sheets])
            return False
        return True
