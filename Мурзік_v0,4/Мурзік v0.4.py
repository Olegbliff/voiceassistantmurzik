import webbrowser
import os
import sys
import subprocess
import winreg
import psutil
import urllib.parse
import threading
import ctypes
import time
import google.generativeai as genai
import speech_recognition as sr
import pygetwindow as gw
import tkinter as tk
import win32com.client as win32  # Для роботи з Microsoft Word
import requests
import winshell

# Імпорти для роботи з віконними дескрипторами
import win32process
import win32gui
import win32con
import pyautogui

# Імпорти для Pillow
from PIL import Image, ImageDraw, ImageTk

# Модуль для сповіщень
import tkinter.messagebox as messagebox

# Імпорти для керування гучністю за допомогою pycaw
from comtypes import CLSCTX_ALL, POINTER, cast
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except ImportError:
    print("Будь ласка, встановіть pycaw та comtypes: pip install pycaw comtypes")


def clear_console():
    # Використовуємо os.system для Windows або Unix/Linux
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')




# Глобальна змінна для збереження історії розмови
conversation_history = []
# Обмеження кількості записів (ви можете задати свій ліміт)
MAX_HISTORY_LENGTH = 20

def add_to_context(user_input, assistant_response):
    """
    Додає новий хід розмови до історії. Якщо історія перевищує MAX_HISTORY_LENGTH,
    видаляє найстаріші записи.
    """
    global conversation_history
    conversation_history.append(f"Користувач: {user_input}")
    conversation_history.append(f"Мурзік: {assistant_response}")
    # Якщо історія занадто велика, обрізаємо її
    if len(conversation_history) > MAX_HISTORY_LENGTH:
        conversation_history[:] = conversation_history[-MAX_HISTORY_LENGTH:]

def get_context():
    """
    Повертає злиту історію розмови як один рядок.
    """
    global conversation_history
    return "\n".join(conversation_history)



###############################################
# Допоміжні функції для сповіщень (Toplevel, автозакриття 1.5 сек)
###############################################
def show_popup(title, message):
    """Відображає спливаюче повідомлення, яке автоматично закривається через 1.5 сек."""
    def popup():
        root = tk.Tk()
        root.withdraw()  # Приховує головне вікно
        popup_window = tk.Toplevel(root)
        popup_window.title(title)
        popup_window.geometry("300x100")
        popup_window.attributes("-topmost", True)
        popup_window.configure(bg="white")
        label = tk.Label(popup_window, text=message, font=("Arial", 12), bg="white")
        label.pack(pady=20)
        root.after(1500, popup_window.destroy)
        root.mainloop()
    threading.Thread(target=popup, daemon=True).start()


def show_error(title, message):
    """Відображає спливаюче повідомлення про помилку, яке автоматично закривається через 1.5 сек."""
    def popup():
        root = tk.Tk()
        root.withdraw()
        popup_window = tk.Toplevel(root)
        popup_window.title(title)
        popup_window.geometry("300x100")
        popup_window.attributes("-topmost", True)
        popup_window.configure(bg="white")
        label = tk.Label(popup_window, text=message, font=("Arial", 12), fg="red", bg="white")
        label.pack(pady=20)
        root.after(1500, popup_window.destroy)
        root.mainloop()
    threading.Thread(target=popup, daemon=True).start()


###############################################
# Функції для анімації (fade‑in / fade‑out)
###############################################
def fade_in(window, duration=2000, steps=20):
    """Анімує появу вікна протягом duration мілісекунд."""
    step_value = 1.0 / steps
    delay = duration // steps

    def _fade(current):
        try:
            window.attributes("-alpha", current)
            if current < 1.0:
                window.after(delay, lambda: _fade(min(current + step_value, 1.0)))
            else:
                window.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

    _fade(0.0)


def fade_out(window, duration=500, steps=20):
    """Анімує зникання вікна протягом duration мілісекунд."""
    step_value = 1.0 / steps
    delay = duration // steps

    def _fade(current):
        try:
            window.attributes("-alpha", current)
            if current > 0:
                window.after(delay, lambda: _fade(max(current - step_value, 0.0)))
            else:
                window.destroy()
        except tk.TclError:
            pass

    _fade(1.0)


def extract_executable_path(command):
    """
    Витягує шлях до виконуваного файлу з рядка команди.
    Якщо команда починається з лапок, повертається все до наступної лапки.
    Інакше повертається перше слово.
    """
    command = command.strip()
    if command.startswith('"'):
        match = re.match(r'"([^"]+)"', command)
        if match:
            return match.group(1)
    else:
        return command.split()[0]
    return None

def search_exe_in_directory(directory, program_keyword=None):
    """
    Сканує вказаний каталог та шукає всі файли з розширенням .exe.
    Якщо задано program_keyword, спершу шукаємо exe, в імені якого міститься ключове слово.
    Якщо збігів немає, повертає перший знайдений exe.
    """
    candidates = []
    try:
        for file in os.listdir(directory):
            if file.lower().endswith(".exe"):
                candidates.append(file)
        if program_keyword:
            keyword_l = program_keyword.lower()
            for file in candidates:
                if keyword_l in file.lower():
                    return os.path.join(directory, file)
        if candidates:
            return os.path.join(directory, candidates[0])
    except Exception as e:
        print(f"Помилка при пошуку exe в каталозі {directory}: {e}")
    return None


def find_program_install_path(program_keyword):
    r"""
    Розширений пошук програми за ключовим словом.
    Спочатку перевіряє записи в HKLM (звичайний та WOW6432Node) і HKCU,
    а потім шукає в HKCR\Applications.
    Якщо знаходить відповідний запис – намагається отримати шлях через 'DisplayIcon'
    або 'InstallLocation'. Якщо отриманий шлях вказує на каталог, то шукає в ньому .exe файл,
    який відповідає program_keyword.
    """
    # Шляхи з Uninstall
    reg_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
    ]

    for root, reg_path in reg_roots:
        try:
            key = winreg.OpenKey(root, reg_path)
        except Exception:
            continue
        try:
            count_subkeys, _, _ = winreg.QueryInfoKey(key)
        except Exception:
            continue
        for i in range(count_subkeys):
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name)
            except Exception:
                continue

            try:
                display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
            except Exception:
                continue

            if program_keyword.lower() in display_name.lower():
                # Спробуємо отримати шлях з DisplayIcon
                try:
                    display_icon, _ = winreg.QueryValueEx(subkey, "DisplayIcon")
                    candidate = display_icon.split(",")[0].strip()
                    if os.path.exists(candidate):
                        # Якщо candidate – каталог, спробуємо знайти exe в ньому
                        if os.path.isdir(candidate):
                            exe_candidate = search_exe_in_directory(candidate, program_keyword)
                            if exe_candidate:
                                return exe_candidate
                        else:
                            return candidate
                except Exception:
                    pass

                # Якщо DisplayIcon не дав результату – пробуємо InstallLocation
                try:
                    install_location, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                    if install_location and os.path.exists(install_location):
                        # Якщо InstallLocation – каталог, шукаємо в ньому exe файл
                        if os.path.isdir(install_location):
                            exe_candidate = search_exe_in_directory(install_location, program_keyword)
                            if exe_candidate:
                                return exe_candidate
                            else:
                                # Якщо exe не знайдено, повертаємо InstallLocation (але бажано exe)
                                return install_location
                        else:
                            return install_location
                except Exception:
                    pass
        winreg.CloseKey(key)

    # Розширений пошук у HKEY_CLASSES_ROOT\Applications
    try:
        key_app = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Applications")
        count_subkeys_app, _, _ = winreg.QueryInfoKey(key_app)
        for i in range(count_subkeys_app):
            try:
                subkey_name = winreg.EnumKey(key_app, i)
                if program_keyword.lower() in subkey_name.lower():
                    try:
                        subkey_command = winreg.OpenKey(key_app, subkey_name + r"\shell\open\command")
                        command_value, _ = winreg.QueryValueEx(subkey_command, "")
                        exe_candidate = extract_executable_path(command_value)
                        if exe_candidate and os.path.exists(exe_candidate):
                            return exe_candidate
                    except Exception:
                        continue
            except Exception:
                continue
        winreg.CloseKey(key_app)
    except Exception:
        pass

    return None

def get_desktop_path():
    """Отримує правильний шлях до робочого столу користувача."""
    try:
        return winshell.desktop()
    except Exception as e:
        print(f"Помилка при визначенні шляху до робочого столу: {e}")
        return os.path.join(os.path.expanduser("~"), "Desktop")

def get_url_from_url_file(url_file_path):
    """
    Аналізує '.url' файл і повертає URL, якщо його знайдено.
    """
    try:
        with open(url_file_path, "r", encoding="utf-8") as file:
            for line in file:
                if line.startswith("URL="):
                    return line.strip().split("=", 1)[1]
    except Exception as e:
        print(f"Помилка при читанні URL-файлу: {e}")
    return None

def find_shortcut_on_desktop(program_keyword):
    """
    Шукає ярлик (.lnk або .url) на робочому столі за ключовим словом.
    Якщо знайдено - повертає шлях до ярлика або URL.
    """
    desktop_path = get_desktop_path()
    try:
        for file in os.listdir(desktop_path):
            lower_file = file.lower()

            # Пошук звичайного ярлика .lnk
            if lower_file.endswith(".lnk") and program_keyword.lower() in lower_file:
                return os.path.join(desktop_path, file)

            # Пошук URL-ярлика .url
            elif lower_file.endswith(".url") and program_keyword.lower() in lower_file:
                full_path = os.path.join(desktop_path, file)
                url = get_url_from_url_file(full_path)
                if url:
                    return url  # Повертаємо URL для відкриття в браузері

    except Exception as e:
        print(f"Помилка при пошуку ярлика: {e}")
    return None




##############################################
# Функції для роботи з позицією індикатора
##############################################
def load_indicator_position():
    """
    Завантажує позицію індикатора з файлу "indicator_position.txt".
    Якщо даних немає – повертає за замовчуванням (874, 992).
    """
    try:
        with open("indicator_position.txt", "r", encoding="utf-8") as f:
            data = f.read().strip()
            if data:
                parts = data.split(',')
                if len(parts) == 2:
                    return (int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return (927, 1031)


def save_indicator_position(x, y):
    """
    Зберігає позицію індикатора у файлі "indicator_position.txt".
    """
    try:
        with open("indicator_position.txt", "w", encoding="utf-8") as f:
            f.write(f"{x},{y}")
    except Exception as e:
        print("Помилка збереження позиції індикатора:", e)


##############################################
# Функція створення згладженого зеленого кола
##############################################
def create_smooth_circle_image(image_size, circle_margin, fill_color):
    """
    Створює зображення розміром image_size x image_size з згладженими краями.
    """
    scale = 4
    size = image_size * scale
    margin = circle_margin * scale

    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((margin, margin, size - margin, size - margin), fill=255)

    resample_method = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS
    mask = mask.resize((image_size, image_size), resample_method)

    binary_mask = mask.point(lambda p: 255 if p > 128 else 0)
    solid_image = Image.new("RGBA", (image_size, image_size), fill_color)
    solid_image.putalpha(binary_mask)
    return solid_image


##############################################
# Функції для перетягування індикатора
##############################################
def start_move(event):
    """Запам'ятовує початкові координати миші."""
    event.widget.master._x_offset = event.x
    event.widget.master._y_offset = event.y


def on_drag(event):
    """Переміщує Toplevel-вікно і зберігає позицію."""
    global last_indicator_position
    new_x = event.x_root - event.widget.master._x_offset
    new_y = event.y_root - event.widget.master._y_offset
    event.widget.master.geometry(f"+{new_x}+{new_y}")
    last_indicator_position = (new_x, new_y)
    save_indicator_position(new_x, new_y)


##############################################
# Індикатор (Toplevel)
##############################################
indicator_context = None
last_indicator_position = load_indicator_position()


def show_indicator():
    """
    Створює індикатор у новому потоці.
    """
    global indicator_context, last_indicator_position
    if indicator_context and tk.Toplevel.winfo_exists(indicator_context["window"]):
        return

    def _create():
        global indicator_context
        root = tk.Tk()
        root.withdraw()
        indicator_window = tk.Toplevel(root)
        indicator_window.overrideredirect(True)
        indicator_window.attributes("-topmost", True)
        indicator_window.attributes("-toolwindow", True)
        indicator_window.configure(bg="magenta")
        indicator_window.wm_attributes("-transparentcolor", "magenta")
        indicator_window.attributes("-alpha", 0.0)

        width, height = 50, 50
        x, y = last_indicator_position
        indicator_window.geometry(f"{width}x{height}+{x}+{y}")

        pil_img = create_smooth_circle_image(50, 5, "green")
        indicator_image = ImageTk.PhotoImage(pil_img, master=indicator_window)
        indicator_window.image = indicator_image

        label = tk.Label(indicator_window, image=indicator_image, bg="magenta")
        label.image = indicator_image
        label.pack()
        label.bind("<ButtonPress-1>", start_move)
        label.bind("<B1-Motion>", on_drag)

        fade_in(indicator_window, duration=2000, steps=20)
        indicator_context = {"root": root, "window": indicator_window}
        root.mainloop()

    threading.Thread(target=_create, daemon=True).start()


def hide_indicator():
    global indicator_context
    if indicator_context and tk.Toplevel.winfo_exists(indicator_context["window"]):
        fade_out(indicator_context["window"], duration=500, steps=20)
        _root = indicator_context["root"]
        indicator_context["window"].after(600, lambda: _root.destroy())
        indicator_context = None


##############################################
# Функції для керування гучністю за допомогою pycaw
##############################################
def get_volume_interface():
    """Отримує об'єкт інтерфейсу для керування системним рівнем гучності."""
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    return volume


def get_current_volume_percentage():
    """Повертає поточну гучність як ціле число від 0 до 100."""
    volume = get_volume_interface()
    current = volume.GetMasterVolumeLevelScalar()  # Значення від 0.0 до 1.0
    return int(round(current * 100))


def set_volume_percentage(percentage):
    """Встановлює рівень гучності. Значення обмежується від 0 до 100%."""
    percentage = max(0, min(percentage, 100))
    new_volume = percentage / 100.0
    volume = get_volume_interface()
    volume.SetMasterVolumeLevelScalar(new_volume, None)


def volume_up():
    """Збільшує гучність на 15%, не перевищуючи 100%."""
    current = get_current_volume_percentage()
    new_volume = min(current + 15, 100)
    set_volume_percentage(new_volume)
    print(f"Гучність збільшено до {new_volume}%.")


def volume_down():
    """Зменшує гучність на 15%, не опускаючись нижче 0%."""
    current = get_current_volume_percentage()
    new_volume = max(current - 15, 0)
    set_volume_percentage(new_volume)
    print(f"Гучність зменшено до {new_volume}%.")


def volume_mute():
    """Встановлює гучність рівно 0% (режим 'тиха')."""
    set_volume_percentage(0)
    print("Гучність зменшено до 0% (тиха).")

def next_track():
    """Симулює натискання клавіші для перемикання на наступний трек."""
    VK_MEDIA_NEXT_TRACK = 0xB0
    KEYEVENTF_EXTENDEDKEY = 0x1
    KEYEVENTF_KEYUP = 0x2
    # Натискання клавіші
    ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, KEYEVENTF_EXTENDEDKEY, 0)
    time.sleep(0.05)
    # Відпускання клавіші
    ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

def previous_track():
    """Симулює натискання клавіші для переходу до попереднього треку."""
    VK_MEDIA_PREV_TRACK = 0xB1
    KEYEVENTF_EXTENDEDKEY = 0x1
    KEYEVENTF_KEYUP = 0x2
    # Натискання клавіші
    ctypes.windll.user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, KEYEVENTF_EXTENDEDKEY, 0)
    time.sleep(0.05)
    # Відпускання клавіші
    ctypes.windll.user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def pause_track():
    """Симулює натискання клавіші Play/Pause для призупинення/відновлення відтворення медіа."""
    VK_MEDIA_PLAY_PAUSE = 0xB3
    KEYEVENTF_EXTENDEDKEY = 0x1
    KEYEVENTF_KEYUP = 0x2
    ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


##############################################
# Функції системного керування
##############################################
def shutdown_computer():
    """Вимикає комп'ютер."""
    try:
        # /s - вимкнення, /t 0 - негайно, /f - примусове завершення додатків
        os.system("shutdown /s /t 5 /f")
    except Exception as e:
        print("Помилка при вимкненні комп'ютера:", e)


def reboot_computer():
    """Перезавантажує комп'ютер."""
    try:
        # /r - перезавантаження, /t 0 - негайно, /f - примусове завершення додатків
        os.system("shutdown /r /t 0 /f")
    except Exception as e:
        print("Помилка при перезавантаженні комп'ютера:", e)


def show_running_programs():
    """Виводить список запущених процесів."""
    print("Мурзік: Запущені процеси:")
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            print(f"{proc.info['pid']}: {proc.info['name']}")
        except Exception:
            continue


##############################################
# Функції для роботи з промтами
##############################################
PROMPT_FILE = "prompts.txt"


def load_prompts():
    """Завантажує збережені промти з файлу."""
    prompts = {}
    if os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(":", 1)
                if len(parts) == 2:
                    prompts[parts[0].strip().lower()] = parts[1].strip()
    return prompts


def save_prompt(name, text):
    """Зберігає новий промт у файл."""
    with open(PROMPT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{name.lower()}: {text}\n")
    print(f"✅ Промт '{name}' збережено.")
    show_popup("Промт", f"Промт '{name}' збережено.")


def apply_prompt(name):
    """Повертає промт за назвою, якщо знайдений."""
    prompts = load_prompts()
    key = name.lower()
    if key in prompts:
        info = f"Промт '{name}' застосовано: {prompts[key]}"
        print(info)
        show_popup("Промт", info)
        return prompts[key]
    else:
        err = f"Промт '{name}' не знайдено."
        print(err)
        show_error("Промт", err)
        return None


##############################################
# Функція для відкриття Microsoft Word і вставки тексту
##############################################
def open_word_and_write(request_text):
    """
    Відкриває Microsoft Word через COM-автоматизацію, створює новий документ,
    вставляє наданий текст, а якщо є ключове слово "реферат", використовується збережений промт
    для реферату (якщо він присутній у файлі) і застосовується базове оформлення.
    """
    try:
        # Якщо в запиті є "реферат", перевіряємо, чи є збережений промт для "реферат"
        if "реферат" in request_text.lower():
            ref_prompt = apply_prompt("реферат")
            if ref_prompt:
                enhanced_request = request_text + "\n" + ref_prompt
            else:
                enhanced_request = request_text
        else:
            enhanced_request = request_text

        # Отримуємо відповідь від Gemini
        answer_text = ask_gemini(enhanced_request)

        # Відкриваємо Microsoft Word і вставляємо відповідь
        word = win32.gencache.EnsureDispatch("Word.Application")
        word.Visible = True
        doc = word.Documents.Add()
        doc.Content.Text = answer_text

        # Якщо запит містить "реферат", застосовуємо базове оформлення
        if "реферат" in request_text.lower():
            doc.Content.Font.Name = "Times New Roman"
            doc.Content.Font.Size = 14
            doc.PageSetup.LeftMargin = word.InchesToPoints(1)
            doc.PageSetup.RightMargin = word.InchesToPoints(1)
            doc.PageSetup.TopMargin = word.InchesToPoints(1)
            doc.PageSetup.BottomMargin = word.InchesToPoints(1)
            if doc.Paragraphs.Count > 0:
                first_para = doc.Paragraphs.Item(1)
                first_para.Alignment = 1  # Центрування
                first_para.Range.Font.Bold = True
        print("Microsoft Word відкрито, відповідь отримана, вставлена та (якщо міститься 'реферат') відформатована.")
        return True
    except Exception as e:
        print(f"Помилка при відкритті Word: {e}")
        return False


##############################################
# Функції для інтеграції з Gemini
##############################################
API_KEY_FILE = "gemini_api_key.txt"

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, "r", encoding="utf-8") as f:
            api_key = f.read().strip()
    else:
        print("!!! УВАГА: API ключ для Gemini буде видимим у консолі !!!")
        try:
            api_key = input("Введіть API ключ для Gemini: ")
        except Exception as e:
            print(f"Помилка введення ключа: {e}")
            sys.exit(1)
        if api_key:
            with open(API_KEY_FILE, "w", encoding="utf-8") as f:
                f.write(api_key)
if not api_key:
    print("Помилка: API ключ для Gemini не було введено.")
    sys.exit(1)

models = {
    "1": "gemini-1.5-flash",
    "2": "gemini-1.5-pro",
    "3": "gemini-2.0-flash",
    "4": "gemini-2.5-pro-exp-03-25"
}
print("\nОберіть модель AI:")
for key in sorted(models.keys()):
    print(f"{key} - {models[key]}")
model_choice = input("Ваш вибір: ").strip()
if model_choice in models:
    working_model_name = models[model_choice]
else:
    print("Невірний вибір. Використовується модель за замовчуванням (gemini-1.5-flash).")
    working_model_name = "gemini-1.5-flash"

try:
    genai.configure(api_key=api_key)
    print("Перевірка API ключа для Gemini...")
    genai.GenerativeModel(working_model_name).generate_content(
        "Привіт",
        generation_config=genai.types.GenerationConfig(max_output_tokens=32768)
    )
    print(f"API ключ для Gemini прийнято. Буде використано модель: {working_model_name}")
except Exception as e:
    print(f"Помилка конфігурації Gemini або недійсний API ключ/модель: {e}")
    sys.exit(1)


def get_program_path(registry_path, value_name, executable_name):
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, registry_path) as key:
            program_path, _ = winreg.QueryValueEx(key, value_name)
            return os.path.join(program_path, executable_name)
    except Exception:
        return None


programs = {
    "steam": get_program_path(r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath",
                              "steam.exe") or "C:\\Program Files (x86)\\Steam\\steam.exe",
    "minecraft": get_program_path(r"SOFTWARE\\Mojang\\Minecraft", "InstallLocation",
                                  "minecraft.exe") or "C:\\Users\\User\\AppData\\Roaming\\.minecraft\\launcher.exe",
    "блокнот": "notepad",
}

websites = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com/",
    "facebook": "https://www.facebook.com",
    "twitter": "https://www.twitter.com",
    "github": "https://www.github.com",
    "soundcloud": "https://www.soundcloud.com/",
    "sound": "https://www.soundcloud.com/",
    "gpt": "https://chatgpt.com/",
    "міса": "http://misa.meduniv.lviv.ua/login/index.php",
    "торрент": "https://itorrents-igruha.org/",
    "шахи": "https://www.chess.com/play",
    "instagram": "https://www.instagram.com/",
    "серіали": "https://uaserials.pro/",
    "фільми": "https://uaserials.pro/",
    "netflix": "https://www.netflix.com/ua/",
    "megogo": "https://megogo.net/ua",
    "монополія": "https://gamesgo.net/uk/monopoly-online/",
    "rozetka": "https://rozetka.com.ua/",
    "sinoptik": "https://sinoptik.ua/pohoda/lviv",
    "olx": "https://www.olx.ua/uk/",
    "tiktok": "https://www.tiktok.com/",
    "tik tok": "https://www.tiktok.com/",
    "prom": "Prom.ua",
    "deep state": "Deepstatemap.live",
    "twitch": "https://www.twitch.tv/",
    "auto.ria": "https://auto.ria.com/uk/",
    "pinterest": "https://pinterest.com/",
    "google drive": "https://drive.google.com/drive/u/0/home",
    "google диск": "https://drive.google.com/drive/u/0/home",
    "telegram web": "https://web.telegram.org/a/",
    "microsoft store": "https://apps.microsoft.com/home?hl=en-us&gl=US",
    "xbox": "https://www.xbox.com/uk-ua?msockid=2e6167cc5f2562852c9d728d5e8263af",
    "amazon": "https://www.amazon.com/",
    "aliexpress": "https://www.aliexpress.com/",
    "dropbox": "https://www.dropbox.com/",
    "apple music": "https://music.apple.com/us/library/songs",
    "apple tv": "https://tv.apple.com/",
    "reddit": "https://www.reddit.com/",
    "microsoft": "https://www.microsoft.com/",
    "watson": "https://www.watson.ua/",
    "whatsapp": "https://web.whatsapp.com/",
    "linkedin": "https://www.linkedin.com/",
    "discord": "https://discord.com/app",
    "imdb": "https://www.imdb.com/",
    "paypal": "https://www.paypal.com/",
    "bbc": "https://www.bbc.com/",
    "bb": "https://www.bbc.com/",
    "cnn": "https://edition.cnn.com/",
    "cn": "https://edition.cnn.com/",
    "the new york times": "https://www.nytimes.com/",
    "new york times": "https://www.nytimes.com/",
    "New york tim": "https://www.nytimes.com/",
    "New york ti": "https://www.nytimes.com/",
    "york ti": "https://www.nytimes.com/",
    "igm": "https://www.ign.com/",
    "ign": "https://www.ign.com/",
    "game spot": "https://www.gamespot.com/",
    "gamespot": "https://www.gamespot.com/",
    "metacritic": "https://www.metacritic.com/",
    "speedrun": "https://www.speedrun.com/",
    "opencritic": "https://opencritic.com/",
    "nexus mod": "https://www.nexusmods.com/",
    "nexus modes": "https://www.nexusmods.com/",
    "nexus": "https://www.nexusmods.com/",
    "copilot": "https://copilot.microsoft.com/",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
    "": "",
}


def ask_gemini(question):
    if not question:
        return "Будь ласка, сформулюй запитання."
    try:
        print("Запит до Gemini:", question)
        model = genai.GenerativeModel(working_model_name)
        detailed_prompt = ""
        full_question = detailed_prompt + question
        response = model.generate_content(
            full_question,
            generation_config=genai.types.GenerationConfig(max_output_tokens=128560)
        )
        print("Отримано відповідь від Gemini.")
        if response.parts:
            answer = "".join(part.text for part in response.parts)
        else:
            answer = "Отримано порожню або незрозумілу відповідь від Gemini."
        return answer
    except Exception as e:
        print(f"Помилка запиту до Gemini API: {e}")
        return "Вибач, сталася помилка при зверненні до Gemini."


def open_notepad_and_write(request_text):
    file_path = "gemini_response.txt"
    try:
        print(f"Мурзік: Запитую у Gemini про '{request_text}'...")
        answer = ask_gemini(request_text)
        with open(file_path, "a", encoding="utf-8") as file:
            file.write(answer + "\n\n")
        subprocess.Popen(["notepad", file_path])
        print(f"Мурзік: Додав відповідь до файлу '{file_path}'.")
    except Exception as e:
        print(f"Мурзік: Помилка при роботі з файлом '{file_path}': {e}")

def search_wikipedia(query):
    url = "https://uk.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "exintro": True,
        "titles": query
    }
    response = requests.get(url, params=params)
    data = response.json()
    pages = data["query"]["pages"]

    for page_id in pages:
        return pages[page_id].get("extract", "Нічого не знайдено")

def search_youtube(query):
    """
    Функція формує URL запиту пошуку YouTube за допомогою query та відкриває його в браузері.
    Якщо потрібно, можна додатково автоматизувати кроки через PyAutoGUI.
    """
    # Формуємо URL із закодованим пошуковим запитом
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)

    # Відкриваємо пошук через webbrowser
    webbrowser.open(search_url)
    print(f"Мурзік: Відкрив YouTube і шукаю '{query}'.")


def close_active_window():
    try:
        active_window = gw.getActiveWindow()
        if active_window is None:
            print("Мурзік: Не вдалося визначити активне вікно.")
            return
        hwnd = active_window._hWnd
        thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        os.system(f"taskkill /PID {pid} /F")
        print(f"Asистент: Закрив застосунок з PID {pid} з заголовком '{active_window.title}'.")
    except Exception as e:
        print(f"Мурзік: Помилка при закритті вікна: {e}")


def minimize_active_window():
    """Згортає поточне активне вікно."""
    try:
        active_window = gw.getActiveWindow()
        if active_window is None:
            print("Мурзік: Не вдалося визначити активне вікно.")
            return

        hwnd = active_window._hWnd
        win32gui.ShowWindow(hwnd, 6)  # 6 означає "Minimize"
        print(f"Мурзік: Згорнув вікно '{active_window.title}'.")
    except Exception as e:
        print(f"Мурзік: Помилка при згортанні вікна: {e}")


def maximize_active_window():
    """Розгортає поточне активне вікно на весь екран."""
    try:
        active_window = gw.getActiveWindow()
        if active_window is None:
            print("Мурзік: Не вдалося визначити активне вікно.")
            return

        hwnd = active_window._hWnd
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)  # SW_MAXIMIZE – розгортання
        print(f"Мурзік: Розгорнув вікно '{active_window.title}'.")
    except Exception as e:
        print(f"Мурзік: Помилка при розгортанні вікна: {e}")

def scroll_down():
    """Емулює прокручування вниз у поточному активному вікні."""
    try:
        pyautogui.scroll(-500)  # Число визначає, на скільки прокрутити вниз
        print("Мурзік: Прокрутив текст вниз.")
    except Exception as e:
        print(f"Мурзік: Помилка при прокручуванні тексту вниз: {e}")


def close_program_by_name(program_name):
    """Закриває процес за назвою програми."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if program_name.lower() in proc.info['name'].lower():
                os.system(f"taskkill /PID {proc.info['pid']} /F")
                print(f"Мурзік: Закрив {proc.info['name']} (PID {proc.info['pid']}).")
                return
        except Exception as e:
            print(f"Помилка при закритті {program_name}: {e}")
    print(f"Мурзік: Не знайдено програму '{program_name}'.")


##############################################
# Функція голосового розпізнавання
##############################################
def listen():
    r = sr.Recognizer()
    r.pause_threshold = 1
    r.phrase_time_limit = None
    with sr.Microphone() as source:
        print("")
        try:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=None)
        except sr.WaitTimeoutError:
            return ""
        except Exception as e:
            print(f"Помилка доступу до мікрофону: {e}")
            return None
    try:
        command = r.recognize_google(audio, language="uk-UA")
        print(f"🔎 Розпізнано: {command}")
        return command.lower()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"Помилка запиту до Google Speech Recognition: {e}")
        return ""
    except Exception as e:
        print(f"Невідома помилка розпізнавання: {e}")
        return ""


##############################################
# Змінна для поточного промту
##############################################
current_prompt = None


##############################################
# Функція для відкриття вікна з доступними голосовими командами
##############################################
def show_commands_window():
    """Відкриває окреме спливаюче вікно із списком доступних голосових команд та інформацією про асистента."""
    def window():
        root = tk.Tk()
        root.title("Доступні голосові команди")
        root.geometry("670x500")
        root.attributes("-topmost", True)
        root.configure(bg="white")

        text = (
            "Голосовий асистент має наступні можливості:\n\n"
    "1. Голосове розпізнавання та текстовий ввід - використовує бібліотеку speech_recognition для перетворення голосових команд у текст, а також підтримує ввід через консоль.\n"
    "2. Обробка команд та системне управління - аналізує команди для керування вікнами, запуску програм, відкриття сайтів, а також виконання системних дій (вимикання, перезавантаження, прокручування тексту тощо).\n"
    "3. Керування гучністю та мультимедіа - взаємодіє з системними налаштуваннями гучності через pycaw, а також емулює мультимедійні клавіші для перемикання треків та відтворення/паузи.\n"
    "4. Графічні індикатори та сповіщення - створює анімований індикатор на основі tkinter і Pillow для візуального зворотного зв’язку, а також відображає спливаючі повідомлення та повідомлення про помилки.\n"
    "5. Інтеграція з Gemini API - формує складні запити (з урахуванням контексту розмови) до Gemini для генерації текстових відповідей, отриманих з AI-сервісу.\n"
    "6. Робота з текстовими редакторами - відкриває Microsoft Word або Notepad, вставляє відповідь від Gemini і застосовує базове форматування (зокрема, для створення рефератів).\n"
    "7. Пошук інформації в Інтернеті - забезпечує можливість виконання запитів до Google, YouTube та Wikipedia для швидкого знаходження інформації.\n\n"
    "Я — голосовий асистент, створений для автоматизації завдань, забезпечення інтерактивної взаємодії з комп’ютером і допомоги у вирішенні різноманітних питань."
    "Мур мяу."

        )
        label = tk.Label(root, text=text, font=("Arial", 12), bg="white", justify="left", anchor="nw", wraplength=580)
        label.pack(expand=True, fill="both", padx=10, pady=10)

        button = tk.Button(root, text="Закрити", command=root.destroy)
        button.pack(pady=10)

        root.mainloop()

    threading.Thread(target=window, daemon=True).start()


##############################################
# Функція обробки команд
##############################################
def process_command(command):
    global current_prompt
    if not command or not command.strip():
        return True

    cmd = command.lower().strip()

 # керування активним вікном

    if cmd == "закрий":
        close_active_window()
        return True

    if cmd == "згорнеш":
        minimize_active_window()
        return True

    if cmd == "розгорнеш":
        maximize_active_window()
        return True

    if cmd == "прокрути вниз" or cmd == "вниз" or cmd == "донизу":
        scroll_down()
        return True

    if cmd.startswith("закрий "):
        program_name = command[len("закрий "):].strip()
        if program_name:
            close_program_by_name(program_name)
        else:
            print("Мурзік: Вкажіть назву програми для закриття.")
        return True


    if cmd == "папа" or cmd == "бувай" or cmd == "вихід" or cmd == "вийди":
        print("Мурзік: До побачення!")
        sys.exit()

    # --- 1. Спеціальні команди, що не пов'язані з "відкрий" ---
    if cmd == "що ти вмієш":
        show_commands_window()
        return True

    # 1.1 Команди керування гучністю
    if ("збіль" in cmd and "гучність" in cmd) or ("біль" in cmd and "гучність" in cmd) or ("збіль" in cmd and "гу" in cmd):
        volume_up()
        print("Мурзік: Збільшую гучність.")
        return True

    if ("зменш" in cmd and "гучність" in cmd) or ("зменш" in cmd and "гу" in cmd):
        volume_down()
        print("Мурзік: Зменшую гучність.")
        return True

    if "тиша" in cmd or "mute" in cmd:
        volume_mute()
        print("Мурзік: Перехід до режиму 'тиха'.")
        return True

    if cmd == "зроби будь ласка тихіше" or cmd == "зроби тихіше":
        volume_down()
        print("Мурзік: Зменшую гучність.")

    if cmd.startswith("пауза"):
        pause_track()
        print("Мурзік: Музику поставлено на паузу.")
        return True

    # 1.2 Команди для відкриття блокноту чи Word з текстом
    if cmd.startswith("відкрий блокнот і напиши"):
        request_text = command[len("відкрий блокнот і напиши"):].strip()
        if request_text:
            open_notepad_and_write(request_text)
        else:
            print("Мурзік: Будь ласка, вкажіть текст для запису.")
        return True

    if cmd.startswith("відкрий word і напиши"):
        request_text = command[len("відкрий word і напиши"):].strip()
        if request_text:
            open_word_and_write(request_text)
        else:
            print("Мурзік: Вкажіть текст для вставки у Word.")
        return True

    # 1.3 Пошук у Google (команда "загугли")
    prefix_google = "загугли"
    if cmd.startswith(prefix_google):
        query = command[len(prefix_google):].strip()
        if query:
            search_url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
            webbrowser.open(search_url)
            print(f"Мурзік: Виконую пошук за запитом: {query}")
        else:
            print("Мурзік: Уточніть, що потрібно загуглити.")
        return True

    # 1.4 Пошук у Wikipedia
    if cmd.startswith("вікіпедія"):
        query = command[len("вікіпедія"):].strip()
        if query:
            result = search_wikipedia(query)
            print(f"Wikipedia: {result}")
        return True

    # 1.5 Пошук на YouTube
    if cmd.startswith("відкрий youtube і знайди"):
        query = command[len("відкрий youtube і знайди"):].strip()
        if query:
            search_youtube(query)
        else:
            print("Мурзік: Будь ласка, вкажи, що саме шукати на YouTube.")
        return True

    # 1.6 Системні команди: завершення, вимкнення, перезавантаження, перемикання треків тощо.
    if (("вимк" in cmd or "закрий" in cmd) and ("комп" in cmd or "ПК" in cmd)):
        shutdown_computer()
        print("Мурзік: Вимикаю комп'ютер.")
        return True

    if (("перезавантаж" in cmd or "рестарт" in cmd) and ("комп" in cmd or "ПК" in cmd)):
        reboot_computer()
        print("Мурзік: Перезавантажую комп'ютер.")
        return True

    if "наступний трек" in cmd or "переключи трек" in cmd or "перемкни трек" in cmd or "next track" in cmd:
        next_track()
        print("Мурзік: Перемикаю на наступний трек.")
        return True

    if "минулий трек" in cmd:
        previous_track()
        previous_track()
        print("Мурзік: Перемикаю на попередній трек.")
        return True

    if cmd == "повтори трек" or cmd == "повтори цей трек":
        previous_track()
        print("Мурзік: Ок, повторюю трек. 🎵🔄")
        return True

    # --- 2. Загальна умова для команд, що починаються із "відкрий" ---
    if cmd.startswith("відкрий"):
        requested_item = command[len("відкрий"):].strip().lower()

        # 2.1 Спроба знайти ярлик на робочому столі (.lnk або .url)
        shortcut_path = find_shortcut_on_desktop(requested_item)
        if shortcut_path:
            if "://" in shortcut_path:  # Якщо це URL (наприклад, steam:// або com.epicgames.launcher://)
                print(f"Мурзік: Відкриваю URL: {shortcut_path}")
                try:
                    os.startfile(shortcut_path)
                except Exception as e:
                    print(f"Мурзік: Помилка при відкритті URL: {e}")
                return True
            else:
                print(f"Мурзік: Знайдено ярлик на робочому столі: {shortcut_path}")
                try:
                    subprocess.Popen(shortcut_path, shell=True)
                except Exception as e:
                    print(f"Мурзік: Помилка при відкритті ярлика: {e}")
                return True

        # 2.2 Перевірка статичних словників (програми)
        if requested_item in programs:
            try:
                subprocess.Popen(programs[requested_item], shell=True)
            except Exception as e:
                print(f"Мурзік: Не вдалося відкрити '{requested_item}' зі словника: {e}")
            return True

        # 2.3 Перевірка статичних словників (сайти)
        elif requested_item in websites:
            try:
                webbrowser.open(websites[requested_item])
            except Exception as e:
                print(f"Мурзік: Не вдалося відкрити сайт '{requested_item}': {e}")
            return True

        # Спроба знайти шлях встановлення програми через реєстр
        exe_path = find_program_install_path(requested_item)
        if exe_path:
            print(f"Мурзік: Знайдено '{requested_item}' за шляхом: {exe_path}")
            try:
                os.startfile(exe_path)
            except Exception as e:
                print(f"Мурзік: Не вдалося запустити '{requested_item}' за шляхом: {e}")
            return True
        else:
            try:
                subprocess.Popen(f'cmd /c start "" "{requested_item}"', shell=True)
            except Exception as e:
                print(f"Мурзік: Не вдалося відкрити '{requested_item}': {e}")
            return True

    # --- 3. Фінальний блок: відправлення запиту до Gemini із загальним контекстом. ---
    full_question = ""
    context_str = get_context()
    if context_str:
        full_question += context_str + "\n"
    full_question += f"Користувач: {command}\nМурзік:"

    # Якщо у запиті міститься слово "реферат" і є активний промт, додати його одноразово:
    if "реферат" in cmd and current_prompt:
        full_question += "\n" + current_prompt
        current_prompt = None  # Деактивувати промт

    print("Викликаю ask_gemini з запитом:", full_question)
    answer = ask_gemini(full_question)
    print("________________________________ \n\n", answer, "\n________________________________")

    add_to_context(command, answer)

    clear_console()
    print("Поточна розмова з Gemini:\n")
    print(get_context())

    return True



##############################################
# Головна частина виконання
##############################################
if __name__ == "__main__":
    current_prompt = None  # Скидання промту при старті сесії
    print("Мурзік: Привіт!")
    print("Для активації голосового вводу скажіть: 'Мурзік ...'")
    print("Для деактивації режиму скажіть: 'дякую'")
    print("Оберіть метод введення:")
    print("1 - Голосовий ввід")
    print("2 - Текстовий ввід")
    choice = input("Ваш вибір: ")
    if choice == "1":
        active_session = False  # Голосова сесія не активна на початку
        while True:
            if not active_session:
                print("Очікую на ключове слово...")
                voice_input = listen()
                if not voice_input or voice_input.strip() == "":
                    continue
                if "мурзік" in voice_input.lower() or "мурзик" in voice_input.lower():
                    show_indicator()
                    # Видаляємо перший варіант ключового слова з голосового вводу (щоб отримати чисту команду)
                    if "мурзік" in voice_input.lower():
                        command = voice_input.lower().replace("мурзік", "", 1).strip()
                    else:
                        command = voice_input.lower().replace("мурзик", "", 1).strip()

                    active_session = True
                    current_prompt = None  # Скидання промту при старті сесії
                    if command:
                        process_command(command)

                else:
                    print("Ключове слово не знайдено. Продовжую прослуховування...")
            else:
                print("Слухаю команду в активному режимі...")
                voice_input = listen()
                if not voice_input or voice_input.strip() == "":
                    continue
                if voice_input.strip() == "дякую":
                    print("Голосовий режим деактиваовано.")
                    hide_indicator()
                    active_session = False
                    current_prompt = None
                    continue
                process_command(voice_input)
    elif choice == "2":
        while True:
            command = input("Введіть команду: ")
            process_command(command)
    else:
        print("Невірний вибір! Запустіть програму знову.")