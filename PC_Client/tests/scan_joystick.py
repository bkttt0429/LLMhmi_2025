import pygame
import time
import os

def scan_joystick():
    os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    if count == 0:
        print("❌ No Joystick Found!")
        return

    js = pygame.joystick.Joystick(0)
    js.init()
    print(f"🎮 Connected: {js.get_name()}")
    print(f"   Axes: {js.get_numaxes()}")
    print(f"   Buttons: {js.get_numbuttons()}")
    print(f"   Hats: {js.get_numhats()}")

    print("\n⚠️  Please move ALL sticks and buttons to see their IDs...")
    print("   (Press Ctrl+C to exit)\n")

    try:
        while True:
            pygame.event.pump()
            
            # Scan Axes
            axes_str = ""
            for i in range(js.get_numaxes()):
                val = js.get_axis(i)
                if abs(val) > 0.1: # Threshold
                    axes_str += f"Ax{i}:{val:.2f} "
            
            # Scan Buttons
            btns_str = ""
            for i in range(js.get_numbuttons()):
                if js.get_button(i):
                    btns_str += f"Btn{i} "
            
            # Scan Hats
            hats_str = ""
            for i in range(js.get_numhats()):
                val = js.get_hat(i)
                if val != (0,0):
                    hats_str += f"Hat{i}:{val} "

            output = f"\rStatus: {axes_str} | {btns_str} | {hats_str}"
            print(output.ljust(80), end="", flush=True)
            
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nDone.")

if __name__ == "__main__":
    scan_joystick()
