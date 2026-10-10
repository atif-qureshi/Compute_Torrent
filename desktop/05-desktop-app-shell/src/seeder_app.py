import customtkinter as ctk
import asyncio
import threading
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / '01-hardware-profiling' / 'src'))
sys.path.insert(0, str(Path(__file__).parent.parent / '02-networking-client' / 'src'))
sys.path.insert(0, str(Path(__file__).parent.parent / '03-docker-sandbox' / 'src'))

from hardware_profiler import HardwareProfiler
from networking_client import NetworkingClient, ClientConfig, ConnectionState

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

class ComputeTorrentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('ComputeTorrent Seeder')
        self.geometry('700x500')
        self.profiler = None
        self.client = None
        self.profile_result = None
        self.is_seeding = False
        self.show_onboarding()
    
    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()
    
    def show_onboarding(self):
        self.clear_screen()
        frame = ctk.CTkFrame(self)
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        title = ctk.CTkLabel(frame, text='ComputeTorrent Seeder', font=('Arial', 24, 'bold'))
        title.pack(pady=20)
        status = ctk.CTkLabel(frame, text='Detecting hardware...', font=('Arial', 14))
        status.pack(pady=10)
        self.after(1000, self.run_profiling)
    
    def run_profiling(self):
        try:
            self.profiler = HardwareProfiler()
            self.profile_result = self.profiler.profile()
            self.show_profile_result()
        except Exception as e:
            self.show_error(f'Hardware detection failed: {e}')
    
    def show_profile_result(self):
        self.clear_screen()
        frame = ctk.CTkFrame(self)
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        title = ctk.CTkLabel(frame, text='Hardware Profile', font=('Arial', 20, 'bold'))
        title.pack(pady=20)
        summary = ctk.CTkTextbox(frame, height=150, width=600)
        summary.pack(pady=20)
        summary.insert('1.0', self.profile_result.summary)
        summary.configure(state='disabled')
        docker_status = 'Docker: Available' if self.profile_result.profile.docker_ok else 'Docker: NOT AVAILABLE'
        docker_label = ctk.CTkLabel(frame, text=docker_status, font=('Arial', 14))
        docker_label.pack(pady=10)
        btn = ctk.CTkButton(frame, text='Start Seeding', command=self.start_seeding, height=40, font=('Arial', 16))
        btn.pack(pady=20)
    
    def start_seeding(self):
        self.is_seeding = True
        self.show_dashboard()
    
    def show_dashboard(self):
        self.clear_screen()
        frame = ctk.CTkFrame(self)
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        title = ctk.CTkLabel(frame, text='ComputeTorrent Seeder', font=('Arial', 20, 'bold'))
        title.pack(pady=10)
        self.status_label = ctk.CTkLabel(frame, text='Status: Ready', font=('Arial', 14))
        self.status_label.pack(pady=10)
        tier_text = f'Tier: {self.profile_result.tier}'
        if self.profile_result.profile.GPU:
            tier_text += f' ({self.profile_result.profile.GPU})'
        tier_label = ctk.CTkLabel(frame, text=tier_text, font=('Arial', 12))
        tier_label.pack(pady=5)
        self.task_label = ctk.CTkLabel(frame, text='Current Task: None', font=('Arial', 12))
        self.task_label.pack(pady=10)
        self.stats_label = ctk.CTkLabel(frame, text='Tasks: 0 | Credits: 0', font=('Arial', 12))
        self.stats_label.pack(pady=10)
        info = ctk.CTkTextbox(frame, height=100, width=600)
        info.pack(pady=20)
        info.insert('1.0', 'Ready to connect to coordination server.\n\nMake sure mock server is running:\ncd mock-server && python mock_server.py')
        info.configure(state='disabled')
        btn_frame = ctk.CTkFrame(frame)
        btn_frame.pack(pady=20)
        self.pause_btn = ctk.CTkButton(btn_frame, text='Pause', command=self.toggle_pause)
        self.pause_btn.pack(side='left', padx=10)
        quit_btn = ctk.CTkButton(btn_frame, text='Quit', command=self.quit_app)
        quit_btn.pack(side='left', padx=10)
    
    def toggle_pause(self):
        self.status_label.configure(text='Status: Paused (not yet implemented)')
    
    def quit_app(self):
        self.quit()
    
    def show_error(self, message):
        self.clear_screen()
        frame = ctk.CTkFrame(self)
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        title = ctk.CTkLabel(frame, text='Error', font=('Arial', 20, 'bold'), text_color='red')
        title.pack(pady=20)
        error_label = ctk.CTkLabel(frame, text=message)
        error_label.pack(pady=20)
        btn = ctk.CTkButton(frame, text='Retry', command=self.show_onboarding)
        btn.pack(pady=10)

def main():
    app = ComputeTorrentApp()
    app.mainloop()

if __name__ == '__main__':
    main()
