#!/usr/bin/env python3
"""
sep_gui.py — tkinter GUI for SEP → EPUB/PDF conversion.
"""

import os
import sys
import threading
import queue

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from sep_app import convert


# ─── Theme colours ────────────────────────────────────────────────

CARDINAL = '#8C1515'
CARDINAL_LIGHT = '#A34D4D'
BG = '#FAFAFA'
FG = '#333'


# ─── GUI Application ──────────────────────────────────────────────

class SEPConverterApp:
    """Main tkinter application window."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title('SEP Converter · 斯坦福哲学百科转换器')
        self.root.geometry('760x760')
        self.root.minsize(700, 700)
        self.root.configure(bg=BG)

        # Set window icon (fallback if no icon file)
        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

        self._build_ui()
        self._running = False
        self._msg_queue = queue.Queue()
        self._poll_queue()

    # ─── UI Build ──────────────────────────────────────────────

    def _build_ui(self):
        root = self.root
        pad = {'padx': 12, 'pady': 4}

        # ── Title bar ──
        title_frame = tk.Frame(root, bg=CARDINAL, height=48)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)
        tk.Label(title_frame, text='斯坦福哲学百科 → EPUB / PDF / TXT',
                 fg='white', bg=CARDINAL,
                 font=('Source Sans Pro', 14, 'bold')).pack(pady=10)

        main = tk.Frame(root, bg=BG, padx=16, pady=12)
        main.pack(fill='both', expand=True)

        # ── URLs ──
        tk.Label(main, text='词条链接（每行一篇）：',
                 anchor='w', bg=BG, fg=FG, font=('', 10)).pack(fill='x', **pad)
        url_frame = tk.Frame(main, bg=BG)
        url_frame.pack(fill='both', expand=True, **pad)
        self.url_text = tk.Text(url_frame, height=6, width=70,
                                 font=('Consolas', 10), wrap='word',
                                 relief='solid', borderwidth=1)
        scroll_y = tk.Scrollbar(url_frame, command=self.url_text.yview)
        self.url_text.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side='right', fill='y')
        self.url_text.pack(side='left', fill='both', expand=True)

        # ── Options row ──
        opt_frame = tk.Frame(main, bg=BG)
        opt_frame.pack(fill='x', pady=(8, 0))

        # Format
        fmt_frame = tk.Frame(opt_frame, bg=BG)
        fmt_frame.pack(side='left', padx=(12, 30))
        tk.Label(fmt_frame, text='输出格式：', bg=BG, fg=FG,
                 font=('', 10)).pack(anchor='w')
        self.fmt_var = tk.StringVar(value='pdf')
        tk.Radiobutton(fmt_frame, text='EPUB', variable=self.fmt_var,
                       value='epub', bg=BG, fg=FG, command=self._format_changed,
                       selectcolor='white', font=('', 10)).pack(anchor='w')
        tk.Radiobutton(fmt_frame, text='PDF', variable=self.fmt_var,
                       value='pdf', bg=BG, fg=FG, command=self._format_changed,
                       selectcolor='white', font=('', 10)).pack(anchor='w')
        tk.Radiobutton(fmt_frame, text='TXT（纯文本）', variable=self.fmt_var,
                       value='txt', bg=BG, fg=FG, command=self._format_changed,
                       selectcolor='white', font=('', 10)).pack(anchor='w')

        # Embed images
        embed_frame = tk.Frame(opt_frame, bg=BG)
        embed_frame.pack(side='left', padx=(0, 30))
        tk.Label(embed_frame, text='图片选项：', bg=BG, fg=FG,
                 font=('', 10)).pack(anchor='w')
        self.embed_var = tk.BooleanVar(value=True)
        self.embed_check = tk.Checkbutton(embed_frame, text='嵌入图片（TXT 仅保留说明）',
                       variable=self.embed_var,
                       bg=BG, fg=FG, selectcolor='white',
                       font=('', 10))
        self.embed_check.pack(anchor='w')

        # ── Output mode ──
        mode_frame = tk.Frame(main, bg=BG)
        mode_frame.pack(fill='x', pady=(8, 0))
        tk.Label(mode_frame, text='输出方式：',
                 bg=BG, fg=FG, font=('', 10)).pack(anchor='w', **pad)
        mode_radio_frame = tk.Frame(mode_frame, bg=BG)
        mode_radio_frame.pack(fill='x', **pad)
        self.mode_var = tk.StringVar(value='separate')
        tk.Radiobutton(mode_radio_frame, text='每篇一个文件',
                       variable=self.mode_var, value='separate',
                       bg=BG, fg=FG, selectcolor='white',
                       command=self._toggle_filename,
                       font=('', 10)).pack(side='left', padx=(0, 20))
        tk.Radiobutton(mode_radio_frame, text='多篇合并为一个文件',
                       variable=self.mode_var, value='merge',
                       bg=BG, fg=FG, selectcolor='white',
                       command=self._toggle_filename,
                       font=('', 10)).pack(side='left')

        # ── Filename (merge mode only) ──
        name_frame = tk.Frame(main, bg=BG)
        name_frame.pack(fill='x', pady=(4, 0))
        tk.Label(name_frame, text='文件名（仅合并时可填；留空自动命名，不用填写扩展名）：',
                 bg=BG, fg=FG, font=('', 9)).pack(anchor='w', **pad)
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(name_frame, textvariable=self.name_var,
                                    font=('', 10), state='disabled',
                                    relief='solid', borderwidth=1)
        self.name_entry.pack(fill='x', **pad)

        # ── Output directory ──
        dir_frame = tk.Frame(main, bg=BG)
        dir_frame.pack(fill='x', pady=(4, 0))
        tk.Label(dir_frame, text='保存目录：',
                 bg=BG, fg=FG, font=('', 10)).pack(anchor='w', **pad)
        dir_input_frame = tk.Frame(dir_frame, bg=BG)
        dir_input_frame.pack(fill='x', **pad)
        self.dir_var = tk.StringVar(value=os.getcwd())
        self.dir_entry = tk.Entry(dir_input_frame, textvariable=self.dir_var,
                                   font=('Consolas', 9), relief='solid',
                                   borderwidth=1)
        self.dir_entry.pack(side='left', fill='x', expand=True)
        tk.Button(dir_input_frame, text='选择目录…',
                  command=self._browse_dir,
                  bg='#eee', relief='raised',
                  font=('', 9)).pack(side='left', padx=(6, 0))

        # ── Convert button ──
        self.convert_btn = tk.Button(main, text='开始转换',
                                      command=self._on_convert,
                                      bg=CARDINAL, fg='white',
                                      activebackground=CARDINAL_LIGHT,
                                      activeforeground='white',
                                      font=('', 12, 'bold'),
                                      relief='raised', borderwidth=1,
                                      cursor='hand2', height=1)
        self.convert_btn.pack(fill='x', padx=12, pady=(12, 4), ipady=6)

        # ── Log ──
        tk.Label(main, text='运行记录：',
                 anchor='w', bg=BG, fg=FG, font=('', 10)).pack(fill='x', **pad)
        log_frame = tk.Frame(main, bg=BG)
        log_frame.pack(fill='both', expand=True, **pad)
        self.log_text = tk.Text(log_frame, height=8, width=70,
                                 font=('Consolas', 9), wrap='word',
                                 state='disabled', relief='solid',
                                 borderwidth=1, bg='#f5f5f5')
        scroll_log = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll_log.set)
        scroll_log.pack(side='right', fill='y')
        self.log_text.pack(side='left', fill='both', expand=True)

    # ─── Callbacks ────────────────────────────────────────────

    def _format_changed(self):
        self.embed_check.configure(state='disabled' if self.fmt_var.get() == 'txt' else 'normal')

    def _toggle_filename(self):
        """Enable/disable filename entry based on output mode."""
        if self.mode_var.get() == 'merge':
            self.name_entry.configure(state='normal')
        else:
            self.name_entry.configure(state='disabled')

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _log(self, msg):
        """Append a line to the log area (thread-safe via queue)."""
        self._msg_queue.put(msg)

    def _poll_queue(self):
        """Periodically drain the message queue onto the log widget."""
        while True:
            try:
                msg = self._msg_queue.get_nowait()
            except queue.Empty:
                break
            if msg is None:
                self._reset_btn()
                continue
            self.log_text.configure(state='normal')
            self.log_text.insert('end', msg + '\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')
        self.root.after(100, self._poll_queue)

    def _on_convert(self):
        if self._running:
            return
        self._running = True
        self.convert_btn.configure(state='disabled', text='正在转换，请稍候…')
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

        # Gather config
        raw = self.url_text.get('1.0', 'end-1c').strip()
        urls = [u.strip() for u in raw.split('\n') if u.strip()]
        if not urls:
            messagebox.showwarning('缺少链接', '请至少输入一个 SEP 词条链接，每行一篇。')
            self._reset_btn()
            return

        fmt = self.fmt_var.get()
        embed = self.embed_var.get() and fmt != 'txt'
        mode = self.mode_var.get()
        name = self.name_var.get().strip() or None
        out_dir = self.dir_var.get().strip() or '.'

        config = {
            'urls': urls,
            'format': fmt,
            'embed_images': embed,
            'output_mode': mode,
            'output_name': name if mode == 'merge' else None,
            'output_dir': out_dir,
            'on_status': self._log,
        }

        # Run in background thread
        t = threading.Thread(target=self._do_convert, args=(config,),
                             daemon=True)
        t.start()

    def _do_convert(self, config):
        try:
            paths = convert(config)
            self._log(f'\n已生成 {len(paths)} 个文件：')
            for p in paths:
                sz = os.path.getsize(p)
                self._log(f'  {p}  ({sz/1024:.1f} KB)')
        except Exception as e:
            self._log(f'\n转换失败：{e}')
        finally:
            self._msg_queue.put(None)

    def _reset_btn(self):
        self._running = False
        self.convert_btn.configure(state='normal', text='开始转换')

    # ─── Run ──────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


def run_gui():
    """Launch the GUI (called from sep.py)."""
    app = SEPConverterApp()
    app.run()


if __name__ == '__main__':
    run_gui()
