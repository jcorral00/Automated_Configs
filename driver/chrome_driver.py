from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import subprocess


class Driver:
    def __init__(self, headless: bool = True):
        self.driver = self.iniciar_chrome(headless=headless)

    def iniciar_chrome(self, headless: bool = True):

        # Opciones de chrome
        options = Options()

        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-gpu")  # en Windows evita algunos glitches

        user_agent = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36')
        options.add_argument(f"user-agent={user_agent}")
        # options.add_argument('--start-maximized')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-features=Default')
        options.add_argument(
            '--no-default-browser-check')
        options.add_argument('--disable-notifications')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--no-sandbox')
        options.add_argument('--log-level=3')
        options.add_argument('--allow-running-insecure-content')
        options.add_argument('--no-default-browser-check')
        options.add_argument('--no-first-run')
        options.add_argument('--no-proxy-server')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("--disable-dev-shm-usage")  # útil en contenedores

        # Parámetros a omitir en el inicio de chromedriver
        exp_opt = [
            'enable-automation',
            'ignore-certificate-errors',
            'enable-logging'
        ]
        options.add_experimental_option("excludeSwitches", exp_opt)
        # Parámetros que definen preferencias en chromedriver
        prefs = {
            'profile.default_content_setting_values.notifications': 2,
            'intl.accept_languages': ['es-ES', 'es'],
            'credentials_enable_service': False
        }
        options.add_experimental_option("prefs", prefs)

        service = Service()

        try:
            service.creation_flags = subprocess.CREATE_NO_WINDOW
        except Exception:
            pass

        driver = webdriver.Chrome(options=options, service=service)

        return driver