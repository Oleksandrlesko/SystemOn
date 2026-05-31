# SystemOn

> Десктопний монітор системних ресурсів для **Windows**: CPU, пам’ять, диски, процеси, графіки в реальному часі та сенсори GPU/RAM.

---

## Автор

- **ПІБ**: Лесько Олександр Миколайович
- **Група**: Фес-41
- **Керівник**: Клим Галина Іванівна, доктор технічних наук, професор кафедри радіоелектронних і комп’ютерних систем
- **Дата виконання**: 20.05.2026

---

## Загальна інформація

| Параметр | Значення |
|----------|----------|
| **Тип проєкту** | Десктопний застосунок (Windows) |
| **Мова** | Python 3.10+ |
| **GUI** | PyQt5 |
| **Графіки** | matplotlib (рендер у віджети через `RGraph`) |
| **Моніторинг ОС** | psutil |
| **Збірка .exe** | Nuitka (`build.bat`) |

Детальний опис архітектури — у файлі [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md).

---

## Опис функціоналу

- Моніторинг **CPU** (загальний, по ядрах, по потоках) і **оперативної пам’яті** з графіками
- Вкладка **Processes** — дерево процесів, freeze / unfreeze / terminate
- Вкладка **Drives** — заповненість дисків (назва тому та літера, напр. `Локальний диск (C:)`)
- Вкладка **Sensors** — GPU (через `nvidia-smi`, якщо доступно), частота та обсяг RAM
- **System Information** — вивід `systeminfo` з підтримкою кирилиці
- Теми **Dark / Light**, акцентний колір, швидкість оновлення графіків
- **Плагіни** — розширення через Python-файли (див. [systemonplugins/README.md](systemonplugins/README.md))
- Користувацькі стилі: `~/rmstyle.css`

---

## Основні файли та модулі

| Файл / каталог                | Призначення                                       |
|-------------------------------|---------------------------------------------------|
| `systemon.py`                 | Головне вікно, логіка UI, фоновий збір даних      |
| `components/graph.py`         | Графік `RGraph` (matplotlib → QPixmap)            |
| `style.css`                   | Базові стилі Qt                                   |
| `build.bat`                   | Збірка `SystemOn.exe` (Nuitka, іконка `ICON.ico`) |
| `requirements.txt`            | Залежності для запуску та збірки                  |
| `ICON.ico`                    | Іконка програми (вікно та `.exe` після збірки)    |
| `systemon.png`                | Іконка вікна під час розробки                     |
| `systemonplugins/`            | Приклади плагінів у репозиторії                   |
| `TECHNICAL_DOCUMENTATION.md`  | Технічна документація                             |

---

## Як запустити проєкт «з нуля»

### 1. Інструменти

- **Windows** 10/11
- **Python 3.10+** ([python.org](https://www.python.org/downloads/)) — під час встановлення увімкніть *Add Python to PATH*
- Для **GPU Sensors**: драйвер NVIDIA та `nvidia-smi` у PATH (необов’язково)

### 2. Клонування / копіювання проєкту

```bash
https://github.com/Oleksandrlesko/SystemOn.git
```

### 3. Встановлення залежностей

```bash
pip install -r requirements.txt
```

У `requirements.txt` є пакети для **запуску** (PyQt5, psutil) і для **збірки** (Nuitka, ordered-set).

### 4. Запуск з вихідного коду

```bash
python systemon.py
```

Плагіни підвантажуються з:

1. `%USERPROFILE%\systemonplugins`
2. `systemonplugins\` поруч із `systemon.py`

---

## Збірка portable `.exe`

### Що потрібно

- Виконані кроки вище (`pip install -r requirements.txt`)
- У корені проєкту файл **`ICON.ico`** — іконка для зібраного `.exe` і Windows Explorer
- Для Nuitka на Windows — **компілятор C** (Visual Studio Build Tools з компонентом *Desktop development with C++*, або MinGW64; див. [документацію Nuitka](https://nuitka.net/doc/user-manual.html))

### Команда

```bash
./build.bat
```

Скрипт:

- використовує **`--windows-icon-from-ico=ICON.ico`** — іконка зібраного `SystemOn.exe`;
- підключає `style.css`, `systemon.png`, пакет `components`, каталог `systemonplugins` (якщо є);
- створює **`dist\SystemOn.exe`** (onefile, без консольного вікна).

Якщо `ICON.ico` відсутній, `build.bat` зупиниться з повідомленням про помилку.

---

## Інструкція для користувача

1. **Overview** — картки CPU / Memory / Boot Drive, швидкі дії (тема, швидкість оновлення), System Information, очищення RAM/Temp.
2. **Processes** — картки процесів; вибір чекбоксами; Freeze / Unfreeze / Terminate.
3. **Performance** — режими **Overall**, **Cores**, **Threads**; графік пам’яті внизу.
4. **Drives** — прогрес-бари по дисках.
5. **Sensors** — температура та споживання GPU (якщо є NVIDIA), дані RAM.

Налаштування зберігаються у `%USERPROFILE%\systemon_settings.json`.

---

## Плагіни (коротко)

Створіть `my_plugin.py` у `%USERPROFILE%\systemonplugins` або скопіюйте приклад `systemonplugins\example_smoke_test.py`:

```python
def register_plugin(app_context):
    main_window = app_context["main_window"]
    # ваш код (PyQt5)
```

Деталі — [systemonplugins/README.md](systemonplugins/README.md).

---

## Проблеми і рішення

| Проблема                         | Рішення                                                                                        |
|----------------------------------|------------------------------------------------------------------------------------------------|
| `nuitka` не знайдено             | `pip install -r requirements.txt`                                                              |
| Помилка компіляції Nuitka        | Встановіть Visual Studio Build Tools (C++) або MinGW64                                         |
| `ICON.ico not found`             | Покладіть `ICON.ico` у корінь проєкту поруч із `systemon.py`                                   |
| Кракозябри в System Information  | Перезапустіть програму; на Windows 11 перевірте мовні налаштування; див. технічну документацію |
| GPU Sensors = N/A                | Потрібен NVIDIA GPU і `nvidia-smi` у PATH                                                      |
| Плагін не завантажується         | Перевірте консоль при `python systemon.py`; має бути `register_plugin`                         |

---

## Використані джерела

- [PyQt5 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- [psutil](https://psutil.readthedocs.io/)
- [Nuitka User Manual](https://nuitka.net/doc/user-manual.html)
- [Microsoft systeminfo](https://learn.microsoft.com/windows-server/administration/windows-commands/systeminfo)
