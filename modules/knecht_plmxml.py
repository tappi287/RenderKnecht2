import logging
from queue import Queue

from knechtapp import initialize_log_listener
from modules.language import get_translation
from modules.log import init_logging, setup_logging
from modules.plmxml import PlmXml
from modules.plmxml.configurator import PlmXmlConfigurator
from private.plmxml_example_data import example_pr_string, plm_xml_file

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext

if __name__ == '__main__':
    log_queue = Queue()
    setup_logging(log_queue)
    log_listener = initialize_log_listener(log_queue)
    log_listener.start()

    # -- Parse a PlmXml file, collecting product instances and LookLibrary
    plm_xml = PlmXml(plm_xml_file)

    # -- Let the User enter a PR String for testing
    LOGGER.info('Enter PR String(leave blank for example string):')
    pr_string = input('>>>:')

    if not pr_string:
        pr_string = example_pr_string

    # -- Configure the PlmXml product instances and LookLibrary with a configuration string
    config = PlmXmlConfigurator(plm_xml, pr_string)

    # -- Request to show the updated configuration in DeltaGen, will block
    if not config.request_delta_gen_update():
        for err in config.errors:
            LOGGER.error(err)

    log_listener.stop()
    logging.shutdown()
