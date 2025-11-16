from colorama import Fore

def message_print(messages, border_color=None, role_color=None, title=""):
    border_top = f"\n+++++++ --------------------------{title}--------------------------------- +++++\n"
    border_bottom = "\n+++++++ ----------------------------------------------------------- +++++\n"
    if border_color:
        print(border_color + border_top + Fore.RESET)
    else:
        print(border_top)

    if not isinstance(messages, list):
        print("\nError: The input should be a list of dictionaries.")
        return

    for message in messages:
        role = message.get('role', 'unknown')
        content = message.get('content', '')
        if role_color:
            print(f"{role_color}{role}{Fore.RESET}: {content}\n")
        else:
            print(f"{role}: {content}\n")

    if border_color:
        print(border_color + border_bottom + Fore.RESET)
    else:
        print(border_bottom)

def print_standout_text(text, border_color=None, title="", border_length=59):
    title_length = len(title)

    # Calculate the number of "-" needed for the top border, ensuring total length matches the bottom
    if title_length > 0:
        dashes_on_each_side = (border_length - title_length - 2) // 2
        border_top = f"\n+++++++ {'-' * dashes_on_each_side} {title} {'-' * dashes_on_each_side} +++++\n"
    else:
        border_top = f"\n+++++++ {'-' * border_length} +++++\n"

    border_bottom = f"\n+++++++ {'-' * border_length} +++++\n"

    if border_color:
        print(border_color + border_top + Fore.RESET)
    else:
        print(border_top)

    print(f"\n{text}\n")

    if border_color:
        print(border_color + border_bottom + Fore.RESET)
    else:
        print(border_bottom)
