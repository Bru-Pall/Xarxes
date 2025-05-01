import sys
import socket
import threading

from xarxes2025.udpdatagram import UDPDatagram
from tkinter import Tk, Label, Button, W, E, N, S
from tkinter import messagebox
import tkinter as tk

from loguru import logger

from PIL import Image, ImageTk
import io

class Client(object):
    def __init__(self, server_port, filename, host , udp_port):
        logger.debug(f"Client creat")
        self.server_port = server_port
        self.server_host = host
        self.filename = filename
        self.udp_port = udp_port

        self.rtsp_socket = None
        self.seq = 1
        self.session_id = None

        self.playing = False
        self.paused = False
        self.udp_socket = None

        self.connect_to_server()
        self.create_ui()

    def create_udp_socket(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.udp_socket.bind(('', self.udp_port))
            logger.info(f"UDP socket listening on port {self.udp_port}")
        except Exception as e:
            logger.error(f"Could not bind UDP socket on port {self.udp_port}: {e}")
            messagebox.showerror("UDP Error", f"Port {self.udp_port} is already in use.\nTry another port.")


    def listen_udp(self):
        while True:
            try:
                data, addr = self.udp_socket.recvfrom(65536)
                logger.debug(f"Received UDP packet from {addr}")
                datagrama = UDPDatagram(10,10)
                datagrama.decode(data)
                self.updateMovie(datagrama.get_payload())
            except Exception as e:
                logger.error(f"Error receiving UDP packet: {e}")
                break

    def connect_to_server(self):
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtsp_socket.connect((self.server_host, self.server_port))
            logger.info(f"Conectat a server")
        except Exception as e:
            logger.error(f"Conexio fallada")
            messagebox.showerror("Error conexio", f"NO es pot conectar amb el servidor")

    def send_setup_request(self):
        if self.rtsp_socket is None or self.rtsp_socket._closed:
            logger.error("RTSP socket is not connected")
            return
        request = (
            f"SETUP {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq}\r\n"
            f"Transport: RTP/UDP; client_port = {self.udp_port}\r\n"
        )
        logger.debug(f"Sending SETUP request:\n{request}")
        try:
            self.rtsp_socket.send(request.encode())
            response = self.rtsp_socket.recv(1024).decode()
            logger.debug(f"Rebut del servidor")
            logger.debug(response)
            if "200 OK" in response:
                self.text["text"] = "SETUP OK"
                self.paused = False
            else:
                self.text["text"] = "SETUP FAILED"
        except Exception as e:
            logger.error(f"Fallo d'enviament de SETUP: {e}")
            self.text["text"] = f"error SETUP: {e}"

    def send_play_request(self):
        if self.playing and not self.paused:
            logger.info(f"Already Playing")
            return

        request = (
            f"PLAY {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq + 1}\r\n"
            f"Session: {self.session_id}\r\n"
        )
        logger.debug(f"Sending PLAY request:\n{request}")

        try:
            self.rtsp_socket.send(request.encode())
            response = self.rtsp_socket.recv(1024).decode()
            logger.debug(f"Received PLAY response:\n{response}")

            if "200 OK" in response:
                self.text["text"] = "PLAY OK ✅"
                if self.udp_socket is None:
                    self.create_udp_socket()
                    threading.Thread(target=self.listen_udp, daemon=True).start()
                self.paused = False
                self.playing = True
            else:
                self.text["text"] = "PLAY FAILED ❌"
        except Exception as e:
            logger.error(f"Failed to send PLAY request: {e}")
            self.text["text"] = f"Error PLAY: {e}"

    def send_pause_request(self):
        if not self.playing:
            logger.info("Not playing. Ignoring PAUSE.")
            return

        request = (
            f"PAUSE {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq + 1}\r\n"
            f"Session: {self.session_id}\r\n"
        )
        logger.debug(f"Sending PAUSE request:\n{request}")

        try:
            self.rtsp_socket.send(request.encode())
            response = self.rtsp_socket.recv(1024).decode()
            logger.debug(f"Received PAUSE response:\n{response}")

            if "200 OK" in response:
                self.text["text"] = "PAUSE OK ⏸️"
                self.paused = True
            else:
                self.text["text"] = "PAUSE FAILED ❌"
        except Exception as e:
            logger.error(f"Failed to send PAUSE request: {e}")
            self.text["text"] = f"Error PAUSE: {e}"

    def send_teardown_request(self):
        request = (
            f"TEARDOWN {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq + 1}\r\n"
            f"Session: {self.session_id}\r\n"
        )
        logger.debug(f"Sending TEARDOWN request:\n{request}")
        try:
            if self.rtsp_socket and not self.rtsp_socket._closed:
                self.rtsp_socket.send(request.encode())
                response = self.rtsp_socket.recv(1024).decode()
                logger.debug(f"Received TEARDOWN response:\n{response}")

                if "200 OK" in response:
                    self.text["text"] = "TEARDOWN OK ✅"
                    if self.udp_socket:
                        self.udp_socket.close()
                        self.udp_socket = None
                    self.session_id = None
                    self.playing = False
                    self.paused = False
                    self.seq = 1
                else:
                    self.text["text"] = "TEARDOWN FAILED ❌"
        except Exception as e:
            logger.error(f"Failed to send TEARDOWN request: {e}")
            self.text["text"] = f"Error TEARDOWN: {e}"

    def create_ui(self):
        self.root = Tk()
        self.root.wm_title("RTP Client")
        self.root.protocol("WM_DELETE_WINDOW", self.ui_close_window)

        self.setup = self._create_button("Setup", self.ui_setup_event, 0, 0)
        self.start = self._create_button("Play", self.ui_play_event, 0, 1)
        self.pause = self._create_button("Pause", self.ui_pause_event, 0, 2)
        self.teardown = self._create_button("Teardown", self.ui_teardown_event, 0, 3)

        self.movie = Label(self.root, height=29)
        self.movie.grid(row=1, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

        self.text = Label(self.root, height=3)
        self.text.grid(row=2, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

        return self.root

    def _create_button(self, text, command, row=0, column=0, width=20, padx=3, pady=3 ):
        button = Button(self.root, width=width, padx=padx, pady=pady)
        button["text"] = text
        button["command"] = command
        button.grid(row=row, column=column, padx=2, pady=2)
        return button

    def ui_close_window(self):
        self.playing = False
        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None
        # DO NOT close RTSP socket
        self.root.destroy()
        logger.debug("Window closed")
        sys.exit(0)

    def ui_setup_event(self):
        logger.debug("Setup button clicked")
        self.text["text"] = "Setup button clicked"
        self.send_setup_request()

    def ui_play_event(self):
        logger.debug("Play button clicked")
        self.text["text"] = "Sending PLAY request..."
        if self.rtsp_socket and not self.rtsp_socket._closed:
            self.send_play_request()
        else:
            logger.error("RTSP socket not connected")
            self.text["text"] = "Error: No RTSP connection"

    def ui_pause_event(self):
        logger.debug("Pause button clicked")
        self.text["text"] = "Sending PAUSE request..."
        if self.rtsp_socket and not self.rtsp_socket._closed and not self.paused:
            self.send_pause_request()
        else:
            logger.error("RTSP socket not connected or already paused")
            self.text["text"] = "Error: No RTSP connection"

    def ui_teardown_event(self):
        logger.debug("Teardown button clicked")
        self.text["text"] = "Sending TEARDOWN request..."
        if self.rtsp_socket and not self.rtsp_socket._closed:
            self.send_teardown_request()
        else:
            self.text["text"] = "No RTSP connection"

    def updateMovie(self, data):
        photo = ImageTk.PhotoImage(Image.open(io.BytesIO(data)))
        self.movie.configure(image = photo, height=380) 
        self.movie.photo_image = photo