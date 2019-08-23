from PySide2.QtWidgets import QLineEdit, QPushButton, QGroupBox, QLabel, QComboBox, QToolButton, QCheckBox, QAction

from modules.gui.widgets.button_color import QColorButton
from modules.itemview.model import KnechtSortFilterProxyModel as Kf
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def filter_column_names() -> str:
    """ Filtered column names """
    column_names = ''

    for column in Kf.default_filter_columns:
        column_names += Kg.column_desc[column] + ', '

    return column_names[:-2]


def translate_main_ui(ui):
    """ Translate Main Window Ui loaded from ui file

    :param modules.gui.main_ui.KnechtWindow ui:
    """
    LOGGER.debug('Translating Main Window...')

    filter_text = _('Tippen um Baum zu filtern...')
    filter_status_tip = _('Filtert Bauminhalt nach {}.').format(filter_column_names())
    filter_tool_tip = _('Im Baum tippen um Filter zu starten. 1x Escape löscht den Filter. 2x Escape klappt '
                        'Bauminhalt ein.')
    path_txt = _('Pfad:')

    # --- Info Menu ---
    ui.menuDatei.setTitle(_("Datei"))
    ui.actionBeenden.setText(_("Beenden\tStrg+Q"))

    # --- Info Menu ---
    ui.actionVersionCheck: QAction
    ui.actionVersionCheck.setText(_('Auf Aktualisierungen prüfen...'))
    ui.actionIntro: QAction
    ui.actionWelcome.setText(_('Startseite'))
    ui.actionHelp: QAction
    ui.actionHelp.setText(_('Dokumentation'))

    # --- Filter line edits ---
    ui.lineEdit_Src_filter: QLineEdit
    ui.lineEdit_Src_filter.setPlaceholderText(filter_text)
    ui.lineEdit_Src_filter.setStatusTip(filter_status_tip)
    ui.lineEdit_Src_filter.setToolTip(filter_tool_tip)
    ui.lineEdit_Var_filter: QLineEdit
    ui.lineEdit_Var_filter.setPlaceholderText(filter_text)
    ui.lineEdit_Var_filter.setStatusTip(filter_status_tip)
    ui.lineEdit_Var_filter.setToolTip(filter_tool_tip)
    ui.lineEdit_Ren_filter: QLineEdit
    ui.lineEdit_Ren_filter.setPlaceholderText(filter_text)
    ui.lineEdit_Ren_filter.setStatusTip(filter_status_tip)
    ui.lineEdit_Ren_filter.setToolTip(filter_tool_tip)

    # --- Sort buttons ---
    sort_btn_tip = _('Passt die Spaltenbreite an verfügbare Baumbreite an.')
    ui.pushButton_Src_sort: QPushButton
    ui.pushButton_Src_sort.setStatusTip(sort_btn_tip)
    ui.pushButton_Var_sort: QPushButton
    ui.pushButton_Var_sort.setStatusTip(sort_btn_tip)
    ui.pushButton_Ren_sort: QPushButton
    ui.pushButton_Ren_sort.setStatusTip(sort_btn_tip)

    ui.pushButton_Dest_show: QPushButton
    ui.pushButton_Dest_show.setStatusTip(_('Begrenzt Sichtbarkeit auf User-Presets wenn aktiviert.'))

    # --- Clear buttons ---
    clear_btn_tip = _('Doppelklick leert den Bauminhalt.')
    ui.pushButton_Src_clear: QPushButton
    ui.pushButton_Src_clear.setStatusTip(clear_btn_tip)
    ui.pushButton_delVariants: QPushButton
    ui.pushButton_delVariants.setStatusTip(clear_btn_tip)
    ui.pushButton_delRender: QPushButton
    ui.pushButton_delRender.setStatusTip(clear_btn_tip)

    # --- Variant Editor ---
    ui.plainTextEdit_addVariant_Setname: QLineEdit
    ui.plainTextEdit_addVariant_Setname.setPlaceholderText(_('Variant Set oder String Liste'))
    ui.plainTextEdit_addVariant_Setname.setStatusTip(
        _('Zeichenketten mit Zeilenumbruch/Leerzeichen/Semikolon '
          'erstellen mehrere Varianten. Copy und Paste aus PR String Liste, '
          'Excel Suche oder Varianten.cmd Files möglich.'))
    ui.plainTextEdit_addVariant_Variant: QLineEdit
    ui.plainTextEdit_addVariant_Variant.setPlaceholderText('on')
    ui.plainTextEdit_addVariant_Variant.setStatusTip(_('Variante bzw. der Variantenschalter. Text ohne Semikolon '
                                                       ' oder Sonderzeichen.'))
    ui.pushButton_addVariant: QPushButton
    ui.pushButton_addVariant.setStatusTip(_('Fügt eingegebenen Text der Varianten Liste hinzu.'))

    # --- DeltaGen Controller ---
    ui.deltaGenBox: QGroupBox
    ui.deltaGenBox.setTitle('DeltaGen')
    ui.label_ViewerSize: QLabel
    ui.label_ViewerSize.setText(_('Viewer Größe'))
    ui.comboBox_ViewerSize: QComboBox
    ui.comboBox_ViewerSize.setStatusTip(_('Ändert die Viewer Größe der Szene der aktiven DeltaGen Instanz.'))
    ui.pushButton_Bgr: QColorButton
    ui.pushButton_Bgr.setStatusTip(_('Ändert die globale DeltaGen Viewer Hintergrund Farbe. '
                                     'Diese Einstellung wird optional auch für das Rendering verwendet.'))
    ui.pushButton_abort: QPushButton
    ui.pushButton_abort.setStatusTip(_('Bricht laufende Sendung an DeltaGen ab.'))

    # --- Rendering Controller ---
    ui.renderGroupBox: QGroupBox
    ui.renderGroupBox.setTitle(_('Rendering'))
    ui.label_renderTimeDesc: QLabel
    ui.label_renderTimeDesc.setStatusTip(_('Schätzt anhand horizontaler Auflösung, vorhandener CPU Kerne '
                                           'und Sampling die Renderzeit in Global Illumination.'))
    ui.label_RenderPath: QLabel
    ui.label_RenderPath.setText(path_txt)
    ui.lineEdit_currentRenderPath: QLineEdit
    ui.lineEdit_currentRenderPath.setStatusTip(_('Pfad zum Ausgabe Ordner. Wenn kein Pfad angegeben wird, '
                                                 'wird der Render Vorgang abgebrochen.'))
    ui.toolButton_changeRenderPath: QToolButton
    ui.toolButton_changeRenderPath.setStatusTip(_('Datei Dialog um Ausgabe Ordner festzulegen.'))
    ui.checkBox_renderTimeout: QCheckBox
    ui.checkBox_renderTimeout.setText(_('Feedbackloop pro Variante'))
    ui.checkBox_renderTimeout.setStatusTip(
        _('Verhindert unter Umständen das Ausbleiben von Variantenschaltungen wenn DeltaGen '
          'bei aktiviertem RT/GI lange Zeit nicht ansprechbereit ist.'))
    ui.checkBox_applyBg: QCheckBox
    ui.checkBox_applyBg.setText(_('Viewer Hintergrund einstellen'))
    ui.checkBox_applyBg.setStatusTip(_('Verwendet die Viewer Hintergrundfarbe aus dem DeltaGen Einstellungsbereich '
                                       'für die Bildausgabe.'))
    ui.checkBox_createPresetDir: QCheckBox
    ui.checkBox_createPresetDir.setText(_('Render Preset Unterordner erstellen'))
    ui.checkBox_createPresetDir.setStatusTip(_('Erstellt einen Unterordner benannt nach dem Render Preset.'))
    ui.checkBox_convertToPng: QCheckBox
    ui.checkBox_convertToPng.setText(_('Bilder zu PNG konvertieren'))
    ui.checkBox_convertToPng.setStatusTip(_('Konvertiert die ausgegebenen Bilder nach dem Render Vorgang in PNG.'))
    ui.pushButton_startRender: QPushButton
    ui.pushButton_startRender.setText(_('Rendering starten'))
    ui.pushButton_startRender.setStatusTip(_('Startet den Render Vorgang.'))
    ui.pushButton_abortRender: QPushButton
    ui.pushButton_abortRender.setStatusTip(
        _('Bricht laufenden Render Vorgang ab. DeltaGen wird den zuletzt erhaltenen Render Befehl unabhängig '
          'hiervon durchführen.'))

    # --- Pfadaeffchen Controller ---
    ui.pathRefreshBtn: QPushButton
    ui.pathRefreshBtn.setStatusTip(_('Job Manager aktualisieren.'))
    ui.label_PfadAeffchen: QLabel
    ui.label_PfadAeffchen.setText(_('Pfad Render Dienst'))
    ui.pathBtnHelp: QPushButton
    ui.pathBtnHelp.setStatusTip(_('Online Hilfe zum Pfad Render Service aufrufen.'))
    ui.pathConnectBtn: QPushButton
    ui.pathConnectBtn.setStatusTip(_('Verbindung zum Render Service herstellen oder beenden.'))
    ui.jobBox: QGroupBox
    ui.jobBox.setTitle(_('Joberstellung'))
    ui.pathJobNameLineEdit: QLineEdit
    ui.pathJobNameLineEdit.setPlaceholderText(_('Job Namen eingeben (optional)'))
    ui.labelOutputDir: QLabel
    ui.labelOutputDir.setText(_('Ausgabe Verzeichnis'))
    ui.labelOutputDir_2: QLabel
    ui.labelOutputDir_2.setText(_('Szenendatei - CSB Datei *.csb oder MayaBinary *.mb'))
    ui.label_scene_file: QLabel
    ui.label_scene_file.setText(path_txt)
    ui.label_output: QLabel
    ui.label_output.setText(path_txt)
    ui.checkBoxMayaDeleteHidden: QCheckBox
    ui.checkBoxMayaDeleteHidden.setText(_('Maya versteckte Objekte löschen'))
    ui.checkBoxMayaDeleteHidden.setStatusTip(
        _('Bei Problemen mit verschachtelten, versteckten Instanzen deaktivieren. Erhöht die Renderzeit bei großen '
          'Szenen auf TAGE!!!'))
    ui.checkBoxCsbIgnoreHidden: QCheckBox
    ui.checkBoxCsbIgnoreHidden.setText(_('CSB Verstecke Objekte ignorieren'))
    ui.checkBoxCsbIgnoreHidden.setStatusTip(
        _('Dem CSB Importer befehlen versteckte Objekte zu ignorieren. Beschleunigt den Importvorgang enorm. '
          'Bei Problemen deaktivieren.'))
    ui.label_output_2: QLabel
    ui.label_output_2.setText(_('Renderer:'))
    ui.rendererBox: QComboBox
    ui.rendererBox.setStatusTip(_('Den zu verwendenden Renderer wählen.'))
    ui.pathJobSendBtn: QPushButton
    ui.pathJobSendBtn.setText(_('Job übertragen'))

    LOGGER.debug('Translation finished.')
