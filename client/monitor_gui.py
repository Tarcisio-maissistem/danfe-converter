import json
import time
import os
import tkinter as tk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "status.json")

def ler_status():
    if not os.path.exists(STATUS_FILE):
        return "INICIANDO", ""

    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data["status"], data["detalhe"]

def atualizar():
    status, detalhe = ler_status()
    lbl_status.config(text=f"Status: {status}")
    lbl_detalhe.config(text=f"Detalhe: {detalhe}")
    root.after(1000, atualizar)

root = tk.Tk()
root.title("Agente DANFE - Status")
root.geometry("400x150")
root.resizable(False, False)

lbl_status = tk.Label(root, text="Status:", font=("Segoe UI", 14))
lbl_status.pack(pady=10)

lbl_detalhe = tk.Label(root, text="", font=("Segoe UI", 10))
lbl_detalhe.pack()

atualizar()
root.mainloop()
