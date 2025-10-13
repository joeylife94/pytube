import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pytube_helper import get_video_streams, download_video, download_audio


class SimpleDownloader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('pytube Tkinter Downloader')
        self.geometry('600x200')

        tk.Label(self, text='YouTube URL').pack(fill='x')
        self.url_entry = tk.Entry(self)
        self.url_entry.pack(fill='x')

        self.mode = tk.StringVar(value='Video')
        ttk.Radiobutton(self, text='Video', variable=self.mode, value='Video').pack(side='left', padx=5)
        ttk.Radiobutton(self, text='Audio', variable=self.mode, value='Audio').pack(side='left', padx=5)

        tk.Button(self, text='Choose Output', command=self.choose_output).pack(side='left', padx=5)
        self.out_label = tk.Label(self, text='')
        self.out_label.pack(side='left')

        tk.Button(self, text='Download', command=self.start_download).pack(side='right', padx=10)

        self.output_folder = '.'

    def choose_output(self):
        d = filedialog.askdirectory()
        if d:
            self.output_folder = d
            self.out_label.config(text=d)

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror('Error', 'Please enter a URL')
            return
        threading.Thread(target=self._download_thread, args=(url,)).start()

    def _download_thread(self, url):
        try:
            streams = get_video_streams(url)
            if self.mode.get() == 'Video':
                stream = streams['progressive'][0] if streams['progressive'] else streams['adaptive_video'][0]
                out = download_video(stream, self.output_folder)
                messagebox.showinfo('Done', f'Downloaded: {out}')
            else:
                stream = streams['audio'][0]
                out = download_audio(stream, self.output_folder)
                messagebox.showinfo('Done', f'Downloaded: {out}')
        except Exception as e:
            messagebox.showerror('Error', str(e))


if __name__ == '__main__':
    app = SimpleDownloader()
    app.mainloop()
