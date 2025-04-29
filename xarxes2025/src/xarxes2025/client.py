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
    def __init__(self, server_port, filename, host , udp_port ):
           
        """
        Initialize a new VideoStreaming client.

        :param port: The port to connect to.
        :param filename: The filename to ask for to connect to.
        """
        logger.debug(f"Client creat")
        self.server_port = server_port
        self.server_host = host
        self.filename = filename
        self.udp_port = udp_port

        self.rtsp_socket = None
        self.seq = 1
        self.session_id = None

        self.create_ui()

    def create_udp_socket(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('', self.udp_port))  # '' per escoltar en totes les IP locals
        logger.info(f"UDP socket listening on port {self.udp_port}")

    def listen_udp(self):
        while True:
            try:
                data, addr = self.udp_socket.recvfrom(65536)
                logger.debug(f"Received UDP packet from {addr}")

               # Ara processem el frame rebut
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
            self.send_setup_request()
        
        except Exception as e:
            logger.error(f"Conexio fallada")
            messagebox.showerror("Error conexio", f"NO es pot conectar amb el servidor")
        
    def send_setup_request(self):
        request = (
            f"SETUP {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq}\r\n"
            f"Transport: RTP/UDP; client_port = {self.udp_port}\r\n"
            f"\r\n"
        )
        logger.error(f"Enviant SETUP request:\n{request}")

        try:
            self.rtsp_socket.send(request.encode())

            response = self.rtsp_socket.recv(1024).decode()
            logger.debug(f"Rebut del servidor")

            if "200 OK" in response:
                self.text["text"] = "SETUP OK"
            else:
                self.text["text"] = "SETUP FAILED"
        except Exception as e:
            logger.error(f"Fallo d'enviament de SETUP: {e}")
            self.text["text"] = f"error SETUP: {e}"

    def send_play_request(self):
        request = (
            f"PLAY {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq + 1}\r\n"
            f"Session: {self.session_id}\r\n"
            f"\r\n"
    )
        logger.debug(f"Sending PLAY request:\n{request}")

        try:
            self.rtsp_socket.send(request.encode())
        
            response = self.rtsp_socket.recv(1024).decode()
            logger.debug(f"Received PLAY response:\n{response}")

            if "200 OK" in response:
                self.text["text"] = "PLAY OK ✅"
                # Aquí después deberás abrir un socket UDP para empezar a recibir frames
                self.create_udp_socket()
                threading.Thread(target=self.listen_udp, daemon=True).start()
            else:
                self.text["text"] = "PLAY FAILED ❌"
        except Exception as e:
            logger.error(f"Failed to send PLAY request: {e}")
            self.text["text"] = f"Error PLAY: {e}"

        
    def create_ui(self):
        """
        Create the user interface for the client.

        This function creates the window for the client and its
        buttons and labels. It also sets up the window to call the
        close window function when the window is closed.

        :returns: The root of the window.
        """
        self.root = Tk()

        # Set the window title
        self.root.wm_title("RTP Client")

        # On closing window go to close window function
        self.root.protocol("WM_DELETE_WINDOW", self.ui_close_window)


		# Create Buttons
        self.setup = self._create_button("Setup", self.ui_setup_event, 0, 0)
        self.start = self._create_button("Play", self.ui_play_event, 0, 1)
        # self.pause = self._create_button("Pause", self.ui_pause_event, 0, 2)
        # self.teardown = self._create_button("Teardown", self.ui_teardown_event, 0, 3)

        # Create a label to display the movie
        self.movie = Label(self.root, height=29)
        self.movie.grid(row=1, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

        # Create a label to display text messages
        self.text = Label(self.root, height=3)
        self.text.grid(row=2, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

        return self.root
    
    def _create_button(self, text, command, row=0, column=0, width=20, padx=3, pady=3 ):
        """
        Create a button widget with the given text, command, and layout options.

        :param str text: The text to display on the button.
        :param callable command: The function to call when the button is clicked.
        :param int row: The row number of the button in the grid.
        :param int column: The column number of the button in the grid.
        :param int width: The width of the button.
        :param int padx: The horizontal padding of the button.
        :param int pady: The vertical padding of the button.
        :return: The button widget.
        """
        button = Button(self.root, width=width, padx=padx, pady=pady)
        button["text"] = text
        button["command"] = command
        button.grid(row=row, column=column, padx=2, pady=2)
        return button
    
    
    def ui_close_window(self):
        """
        Close the window.
        """
        self.root.destroy()
        logger.debug("Window closed")
        sys.exit(0)


    def ui_setup_event(self):
        """
        Handle the Setup button click event.
        """
        logger.debug("Setup button clicked")
        self.text["text"] = "Setup button clicked"
        
        if not self.rtsp_socket:
            self.connect_to_server()
        self.send_setup_request()

    def ui_play_event(self):
        """
        Handle the Play button click event.
        """
        logger.debug("Play button clicked")
        self.text["text"] = "Sending PLAY request..."

        if self.rtsp_socket:
            self.send_play_request()
        else:
            logger.error("RTSP socket not connected")
            self.text["text"] = "Error: No RTSP connection"


    def updateMovie(self, data):
        """Update the video frame in the GUI from the byte buffer we received."""

        # data hauria de tenir el payload de la imatge extreta del paquet RTP
        # Com no en teniu, encara, us poso un exemple de com carregar una imatge
        # des del disc dur. Això ho haureu de canviar per carregar la imatge
        # des del buffer de bytes que rebem del servidor.
        # photo = ImageTk.PhotoImage(Image.open(io.BytesIO(data)))


        photo = ImageTk.PhotoImage(Image.open(io.BytesIO(data)))
        self.movie.configure(image = photo, height=380) 
        self.movie.photo_image = photo

