from modules.knecht_excel import ExcelData
from modules.knecht_objects import KnData, KnPackage, KnPr, KnTrim
from modules.knecht_utils import list_class_values
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ExcelDataToKnechtData:
    pr_family_cache = dict(PR_Code=('PR_Family_Code', 'PR_Family_Description'))

    def __init__(self, data: ExcelData):
        self.excel_data = data

    def convert(self) -> KnData:
        self.update_pr_family_cache()
        return self.create_data()

    def update_pr_family_cache(self):
        if self.excel_data.pr_options.empty:
            return

        pr_col = self.excel_data.pr_options.columns[self.excel_data.map.Pr.ColumnIdx.pr]
        family_col = self.excel_data.pr_options.columns[self.excel_data.map.Pr.ColumnIdx.family]
        family_desc_col = self.excel_data.pr_options.columns[self.excel_data.map.Pr.ColumnIdx.family_text]

        pr_codes = self.excel_data.pr_options[pr_col].unique()

        for pr in pr_codes:
            pr_rows = self.excel_data.pr_options.loc[self.excel_data.pr_options[pr_col] == pr]
            pr_fam = pr_rows[family_col].unique()[0]
            pr_fam_text = pr_rows[family_desc_col].unique()[0]
            self.pr_family_cache[pr] = (pr_fam, pr_fam_text)

        LOGGER.debug('Indexed %s PR-Codes to PR Families.', len(self.pr_family_cache))

    def create_data(self) -> KnData:
        data = KnData()
        model_column = self.excel_data.models.columns[self.excel_data.map.Models.ColumnIdx.model]

        for idx, model in enumerate(self.excel_data.models[model_column]):
            trim = KnTrim()

            self.update_trim_attributes(model, model_column, trim)
            self.create_pr_options(model, trim)
            self.create_packages(model, trim)

            # Append model/trim to data
            data.models.append(trim)

        data.fakom = self.excel_data.fakom
        self.update_data_attributes(data)

        return data

    def update_data_attributes(self, data: KnData):
        """ Transfer UI options like read_trim etc. """
        for k, v in list_class_values(self.excel_data).items():
            if hasattr(data, k):
                if isinstance(v, (list, bool)):
                    setattr(data, k, v)

    def update_trim_attributes(self, model: str, model_column: str, trim: KnTrim):
        """ Transfer Excel model sheet columns to KnTrim object """
        excel_column_dict = list_class_values(self.excel_data.map.Models.ColumnNames)

        model_rows = self.excel_data.models.loc[self.excel_data.models[model_column] == model]

        for c in self.excel_data.models.columns:
            column_data = model_rows[c].unique()

            if column_data:
                column_data = column_data[0]
            else:
                continue

            # Update KnTrim from ExcelData column data
            for k, v in excel_column_dict.items():
                if v != c:
                    continue
                setattr(trim, k, column_data)

    def create_packages(self, model: str, trim: KnTrim):
        """ Create KnPackage child items for KnTrim parent for model """
        if self.excel_data.packages.empty:
            return

        # Package columns
        pkg_col = self.excel_data.packages.columns[self.excel_data.map.Packages.ColumnIdx.package]
        pkg_text_col = self.excel_data.packages.columns[self.excel_data.map.Packages.ColumnIdx.package_text]
        # PR columns inside package sheet
        pr_col = self.excel_data.packages.columns[self.excel_data.map.Packages.ColumnIdx.pr]
        pr_text_col = self.excel_data.packages.columns[self.excel_data.map.Packages.ColumnIdx.pr_text]

        # Extract rows not matching '-'
        pkg_rows = self.excel_data.packages.loc[~self.excel_data.packages[model].isin(['-'])]

        for pkg, pkg_text in zip(
                pkg_rows[pkg_col].unique(), pkg_rows[pkg_text_col].unique()
                ):
            # Extract package content
            pkg_content = pkg_rows.loc[pkg_rows[pkg_col] == pkg]

            if pkg_content.empty:
                # Skip empty packages
                continue

            # Create package parent item
            pkg_item = KnPackage(trim, pkg, pkg_text)

            for pr, pr_text, pr_value in zip(pkg_content[pr_col], pkg_content[pr_text_col], pkg_content[model]):
                # Get cached PR-Family data
                pr_fam, pr_fam_text = self.pr_family_cache.get(pr)
                # Create PR Option inside Package
                KnPr(pkg_item, pr, pr_text, pr_fam, pr_fam_text, pr_value)

    def create_pr_options(self, model: str, trim: KnTrim):
        if self.excel_data.pr_options.empty:
            return

        # -- PR Columns
        pr_name_col = self.excel_data.pr_options.columns[self.excel_data.map.Pr.ColumnIdx.pr]
        pr_desc_col = self.excel_data.pr_options.columns[self.excel_data.map.Pr.ColumnIdx.pr_text]
        family_name_col = self.excel_data.pr_options.columns[self.excel_data.map.Pr.ColumnIdx.family]
        family_desc_col = self.excel_data.pr_options.columns[self.excel_data.map.Pr.ColumnIdx.family_text]

        for pr_value, pr_name, pr_desc, fam_name, fam_desc in zip(
                self.excel_data.pr_options[model],
                self.excel_data.pr_options[pr_name_col],
                self.excel_data.pr_options[pr_desc_col],
                self.excel_data.pr_options[family_name_col],
                self.excel_data.pr_options[family_desc_col]
                ):
            # Add Trim PR Option
            KnPr(trim, pr_name, pr_desc, fam_name, fam_desc, pr_value)
