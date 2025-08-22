from urllib.parse import urljoin, urlparse
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
import time
from driver.chrome_driver import Driver


class Management:

    def __init__(self, user, pswd):
        self.base_url = 'https://app.smartdatasystem.es'
        self.driver_instance = Driver()
        self.user = user
        self.pswd = pswd
        self.driver = self.driver_instance.iniciar_chrome()
        self.wait = WebDriverWait(self.driver, 100)
        self.auth_url = f'{self.base_url}/?target=auth'
        self.cfgs_url = f'{self.base_url}/?target=powermanagement'
        self.logged_in = False

    def login(self):
        try:
            self.driver.get(self.auth_url)
            username_space = self.driver.find_element(By.XPATH, '//p/input[@id="username"]')
            username_space.send_keys(self.user)
            pswd_space = self.driver.find_element(By.XPATH, '//p/input[@id="password"]')
            pswd_space.send_keys(self.pswd)
            entry_button = self.driver.find_element(By.XPATH, '//p/input[@type="submit"]')
            entry_button.click()
            # Esperamos a un elemento que corrobore que hemos hecho el login:
            self.wait.until(EC.presence_of_element_located(
                (By.XPATH, '//div[@class="gridster ready"]')
            ))
            self.logged_in = True
            return True
        except Exception as e:
            self.logged_in = False
            print(f"Error al intentar hacer el login: {e}")
            return False

    def _init_driver(self):
        if self.driver is None:
            self.driver = self.driver_instance.iniciar_chrome()

    def _is_window_alive(self) -> bool:
        try:
            _ = self.driver.current_window_handle
            return True

        except Exception:
            return False

    def close(self, hard=False):
        try:
            if self.driver:
                (self.driver.quit() if hard else self.driver.quit())
        finally:
            self.driver = None
            self.logged_in = False

    def ensure_session(self):
        self._init_driver()
        if not self._is_window_alive():
            self.close(hard=True)
            self._init_driver()
            self.logged_in = False
        if not self.logged_in:
            self.login()

    def _is_editable(self, el):
        """True si el input está habilitado y no es readonly."""
        if el is None:
            return False
        if not el.is_enabled():
            return False
        if (el.get_attribute("disabled") is not None) or (el.get_attribute("aria-disabled") in ("true", "1")):
            return False
        if (el.get_attribute("readonly") is not None) or (el.get_attribute("aria-readonly") in ("true", "1")):
            return False
        return True

    def _wait_visible(self, by, sel, timeout=20):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((by, sel))
        )

    def _open_link_safely(self, link_el):
        """Abre un <a> tanto si tiene href absoluto/relativo como si es hjavascript: (click)"""
        href_raw = (link_el.get_attribute("href") or "").strip()
        onclick = (link_el.get_attribute("onclick") or "").strip()

        # Si es un enlace JS (o vacío) intenta extraer URL de window.open('...')
        if (not href_raw or href_raw.lower().startswith("javascript")) and onclick:
            import re
            m = re.search(r"window\.open\(['\"]([^'\"]+)", onclick)
            if m:
                href_raw = m.group(1).strip()

        def _should_click(href: str) -> bool:
            if not href:
                return True
            scheme = urlparse(href).scheme.lower()
            return scheme not in ("http", "https", "file") # blob; data; chrome; javascript, etc.

        if _should_click(href_raw):
            before = list(self.driver.window_handles)
            current = self.driver.current_url
            link_el.click()
            # espera cambio de URL o nueva pestaña
            self.wait.until(lambda d: d.current_url != current or len(d.window_handles) > len(before))
            if len(self.driver.window_handles) > len(before):
                self.driver.switch_to.window(self.driver.window_handles[-1])
            return

        edit_url = urljoin(self.base_url, href_raw)

        try:
            self.driver.get(edit_url)
        except WebDriverException as e:
            # Fallback si el driver no soporta el protocolo (o algo raro)
            if "unsupported protocol" in str(e).lower():
                before = list(self.driver.window_handles)
                current = self.driver.current_url
                link_el.click()
                self.wait.until(lambda d: d.current_url != current or len(d.window_handles) > len(before))
                if len(self.driver.window_handles) > len(before):
                    self.driver.switch_to.window(self.driver.window_handles[-1])
            else:
                raise

    # Función para conocer los elementos clave de cada configuración:
    def detect_config(self, cfg, origin=False):
        self.ensure_session()
        self.driver.get(self.cfgs_url)
        time.sleep(2)
        configurations_table = self.wait.until(EC.presence_of_all_elements_located(
            (By.XPATH, '//table[@id="mainTable"]/tbody/tr[position() >= 1]')))

        for config in configurations_table:
            config_name = config.find_element(By.XPATH, './/td[1]').text.strip()
            if config_name == cfg:
                actions_cell = config.find_element(By.XPATH, './/td[6]')
                edit_href = actions_cell.find_element(
                    By.XPATH,
                    ".//div/a[contains(@title,'Modificar configuración')]"
                )
                self._open_link_safely(edit_href)

                last_update = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, '//table[@id="mainTable"]/tbody/tr[1]/td[2]'))).text.strip()

                add_new_change_button = self.driver.find_element(By.XPATH, '//p/input[@name="B4"]')
                add_new_change_button.click()

                # Una vez accedemos a la sección que permite añadir un nuevo cambio buscamos la tarifa:
                tariff = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, '//form[@id="powermanagementrate"]/fieldset/select[@name="timeschemaid"]/option[contains(@selected, "selected")]')
                )).text.strip()

                # Luego, en el caso de que origin = True --> guardamos la info a replicar para mostrarla en la app:

                if origin:
                    # Añadimos las columnas en la lista de claves que compondrán las columnas de nuestro dataframe en la app:
                    cols_xpath = "(//div[@class='scrollabletable']/table/thead/tr/th[1] | " \
                            "//div[@class='scrollabletable']/table/thead/tr/th[position()=2 or position()=5]" \
                            "/p[@class='smalltext'])"

                    target_cols = self.wait.until(EC.presence_of_all_elements_located((By.XPATH, cols_xpath)))

                    keys = []
                    for col in target_cols:
                        txt_col = col.text.strip()
                        keys.append(txt_col)

                    # Añadimos los valores de las filas:
                    rows_xpath = "//div[@class='scrollabletable']/table/tbody/tr[position()>=1]"
                    rows = self.wait.until(EC.presence_of_all_elements_located((By.XPATH, rows_xpath)))

                    data = {k: [] for k in keys}

                    for row in rows:

                        period = row.find_element(By.XPATH, ".//td[1]").text.strip()

                        energy_price = row.find_element(By.XPATH, ".//td[2]/input").get_attribute("value") or ""

                        power_price = row.find_element(By.XPATH, ".//td[5]/input").get_attribute("value") or ""

                        data[keys[0]].append(period)
                        data[keys[1]].append(energy_price)
                        data[keys[2]].append(power_price)

                    return last_update, data, tariff

                else:
                    return last_update, tariff

        raise NoSuchElementException(f"No se encontró la configuración {cfg}")

    def replicate_to(self, destination_cfg: str, data_config: dict, last_updated: str):

        self.ensure_session()
        self.driver.get(self.cfgs_url)
        time.sleep(2)
        configurations_table = self.wait.until(EC.presence_of_all_elements_located(
            (By.XPATH, '//table[@id="mainTable"]/tbody/tr[position() >= 1]')))
        for config in configurations_table:
            config_name = config.find_element(By.XPATH, './/td[1]').text.strip()
            if config_name == destination_cfg:
                actions_cell = config.find_element(By.XPATH, './/td[6]')
                edit_href = actions_cell.find_element(
                    By.XPATH,
                    ".//div/a[contains(@title,'Modificar configuración')]"
                )
                self._open_link_safely(edit_href)
                add_new_change_button = self.driver.find_element(By.XPATH, '//p/input[@name="B4"]')
                add_new_change_button.click()

                # modificamos el campo de la fecha del último cambio a la last_updated de origin:

                # Esperamos a que el formulario estñe en el DOM y visible:
                form_locator = (By.ID, "powermanagementrate")
                self._wait_visible(*form_locator)

                # Si el form está dentro de un iframe, entrar:
                input_locator = (By.XPATH, '//form[@id="powermanagementrate"]/fieldset/input[contains(@class, "hasDatepicker")]')
                # Localizamos el input:
                last_updated_box = self._wait_visible(*input_locator, timeout=30)

                # Al tratarse de un datepicker, muchos son readonly; mejor escribimos con JS:
                try:
                    self.driver.execute_script("""
                    arguments[0].removeAttribute('readonly');
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
                    """, last_updated_box, last_updated)
                except Exception:
                    last_updated_box.clear()
                    last_updated_box.send_keys(last_updated)

                # Modificamos los campos de precio de energía y potencia en función de data_config:
                valid_rows_xpath = "//div[@class='scrollabletable']/table/tbody/tr[not(contains(@style, 'display: none'))]"
                rows = self.wait.until(EC.presence_of_all_elements_located((By.XPATH, valid_rows_xpath)))

                energy_list = data_config.get('(precio/unidad energía)', [])
                power_list = data_config.get('(precio/unidad potencia/día)', [])

                n = min(len(rows), len(energy_list))

                for i, row in enumerate(rows[:n]):
                    try:
                        energy_box = row.find_element(By.XPATH, ".//td[2]/input")
                        energy_box.clear()
                        energy_box.send_keys(energy_list[i])

                        # El campo de potencia en las tarifas 2.0 en la última row está siempre disabled:
                        try:
                            power_box = row.find_element(By.XPATH, ".//td[5]/input")
                        except NoSuchElementException:
                            power_box = None

                        if power_box and self._is_editable(power_box) and i < len(power_list):
                            power_box.clear()
                            power_box.send_keys(power_list[i])

                    except (NoSuchElementException, ElementNotInteractableException):
                        pass

                # Guardamos la configuración:
                save_button = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//p[4][@class='right']/input[@value='Guardar']")
                ))

                save_button.click()

                return last_updated

    def get_config_list(self):

        """Devuelve la lista de configuraciones sin cerrar la sesión ni el driver"""

        self.ensure_session()

        users_attribute = self.wait.until(
            EC.presence_of_element_located((By.XPATH, '//ul[@class="submenu"]/li/a[contains(@href, "?target=users")]')))
        users = users_attribute.get_attribute('href')
        self.driver.get(users)

        try:
            search_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@type="search"]')))
            search_field.clear()
            search_field.send_keys("Irene")
            time.sleep(2)
            user_td_text = self.wait.until(EC.presence_of_element_located((By.XPATH, '//tr[@class="odd"]/td'))).text
            if user_td_text.strip() == "Irene López":
                user_attribute = self.wait.until(EC.presence_of_element_located((By.XPATH, '//a[@title="Iniciar sesión como este usuario"]')))
                user_attribute.click()

            # Acceder a la app de powermanagement:
            self.driver.get(self.cfgs_url)
            time.sleep(2)

        except Exception as e:
            print('Error al intentar acceder al usuario de Irene López. ' + str(e))

        configurations_table = self.wait.until(EC.presence_of_all_elements_located(
            (By.XPATH, '//table[@id="mainTable"]/tbody/tr[position() >= 1]')))

        config_names, seen = [], set()

        for name in configurations_table:
            config_name = name.find_element(By.XPATH, './/td[1]').text.strip()
            if config_name not in seen:
                config_names.append(config_name)
                seen.add(config_name)

        return config_names



