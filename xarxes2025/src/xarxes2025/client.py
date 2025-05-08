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

        #Connection parameters
        self.server_port = server_port
        self.server_host = host
        self.filename = filename
        self.udp_port = udp_port

        # RTSP protocol state
        self.rtsp_socket = None    # TCP socket for RTSP control
        self.seq = 1    #RTSP sequence number
        self.session_id = None    # Server-assigned session ID
        self.state = "INIT"   # State machine: INIT, READY, PLAYING


        self.playing = False
        self.paused = False
        self.udp_socket = None

        # Packets statistics
        self.packets_lost = 0
        self.packets_received = 0
        self.total_packets = 0
        self.last_seq = -1

        # Initialize connection and UI
        self.connect_to_server()
        self.create_ui()

    def create_udp_socket(self):

        """ Create and bind the UDP socket for recieving video packets """

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.udp_socket.bind(('', self.udp_port))
            logger.info(f"UDP socket listening on port {self.udp_port}")
        except Exception as e:
            logger.error(f"Could not bind UDP socket on port {self.udp_port}: {e}")
            messagebox.showerror("UDP Error", f"Port {self.udp_port} is already in use.\nTry another port.")

    def update_packet_stats(self, current_seq):

        """ Udapte packet loss/reception statistics and dsplay them """

        # Detect lost packets
        if self.last_seq != -1 and current_seq > self.last_seq + 1:
            self.packets_lost += current_seq - self.last_seq - 1

        # Udapte packets counters
        self.packets_received += 1
        self.total_packets = self.packets_received + self.packets_lost
        self.last_seq = current_seq

        # Udapte UI
        self.counter["text"] = (
            f"Seq Num:{self.total_packets} Lost:{self.packets_lost} OK:{self.packets_received}"
        )
        self.counter.update_idletasks()

    def listen_udp(self):

        """ UDP listener thread that recieves video packets,
        handles packets decoding, packets statistics (recieves, lost and total) and video frame udaptes """

        while True:
            try:
                # Recieve UDP packet
                data, addr = self.udp_socket.recvfrom(65536)

                # Decode RTP packet
                datagrama = UDPDatagram(10, 10)
                datagrama.decode(data)

                # Udapte statistics an display frame
                current_seq = datagrama.get_seqnum()
                self.update_packet_stats(current_seq)
                self.updateMovie(datagrama.get_payload())

            except Exception as e:
                logger.error(f"Error receiving UDP packet: {e}")
                break

    def connect_to_server(self):

        """ Establish TCP connection to RSTP server """

        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtsp_socket.connect((self.server_host, self.server_port))
            logger.info(f"Conectat a server")
        except Exception as e:
            logger.error(f"Conexio fallada")
            messagebox.showerror("Error conexio", f"NO es pot conectar amb el servidor")

    def send_setup_request(self):

        """ Send RSTP Setup request to initialize streaming session 
        and create udp socket """

        if self.state != "INIT":
            self.text["text"] = "Setup already done"
            return

        # Setup request
        request = (
            f"SETUP {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq}\r\n"
            f"Transport: RTP/UDP; client_port= {self.udp_port}\r\n"
            f"\r\n"
        )
        logger.debug(f"Sending SETUP request:\n{request}")
        try:
            # Send request and wait for response
            self.rtsp_socket.send(request.encode())
            self.seq += 1
            response = self.rtsp_socket.recv(1024).decode()

            if "200 OK" in response:

                # Udapte state and create UDP resources
                self.state = "READY"
                self.paused = False
                if self.udp_socket is None:
                    self.create_udp_socket()
                    threading.Thread(target=self.listen_udp, daemon=True).start()

                # Extract session ID from response
                for line in response.split("\n"):
                    if line.strip().startswith("Session:"):
                        self.session_id = line.split(":")[1].strip()
                        logger.debug(f"Session ID received: {self.session_id}")

                self.text["text"] = (f"Setup done. Session ID:{self.session_id} \n Port: {self.udp_port} opened.(BIND OK)")

            else:
                self.text["text"] = "Setup failed"
        except Exception as e:
            logger.error(f"Fallo d'enviament de SETUP: {e}")
            self.text["text"] = f"error SETUP: {e}"

    def send_play_request(self):

        """ Send RTSP Play request to start streaming"""

        if self.state != "READY":
            self.text["text"] = "Already playing"
            return

        # Play request
        request = (
            f"PLAY {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq}\r\n"
            f"Session: {self.session_id}\r\n"
            f"\r\n"
        )
        logger.debug(f"Sending PLAY request:\n{request}")

        try:
            # Send request and wait for response
            self.rtsp_socket.send(request.encode())
            self.seq += 1
            response = self.rtsp_socket.recv(1024).decode()

            if "200 OK" in response:
                self.text["text"] = "Playing"
                self.state = "PLAYING"
                self.paused = False
                self.playing = True
            else:
                self.text["text"] = "Play failed"
        except Exception as e:
            logger.error(f"Failed to send PLAY request: {e}")
            self.text["text"] = f"Error PLAY: {e}"

    def send_pause_request(self):

        """ Send RTSP Pause request to temporarily stop streaming """

        if self.state != "PLAYING":
            self.text["text"] = "Already paused"
            return

        # Pause request
        request = (
            f"PAUSE {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq}\r\n"
            f"Session: {self.session_id}\r\n"
            f"\r\n"
        )
        logger.debug(f"Sending PAUSE request:\n{request}")

        try:
            # Send request and wait for response
            self.rtsp_socket.send(request.encode())
            self.seq += 1
            response = self.rtsp_socket.recv(1024).decode()

            if "200 OK" in response:
                self.text["text"] = "Paused"
                self.state = "READY"
                self.paused = True
            else:
                self.text["text"] = "Pause failed"
        except Exception as e:
            logger.error(f"Failed to send PAUSE request: {e}")
            self.text["text"] = f"Error PAUSE: {e}"

    def send_teardown_request(self):

        """ Send RSTP Teardown request to terminate session,
        close udp socket and reset state and variables"""

        if self.state == "INIT":
            self.text["text"] = "Can't do teardown right now"
            return

        # Teardown request
        request = (
            f"TEARDOWN {self.filename} RTSP/1.0\r\n"
            f"CSeq: {self.seq}\r\n"
            f"Session: {self.session_id}\r\n"
            f"\r\n"
        )
        try:
            # Send request and wait for response
            if self.rtsp_socket and not self.rtsp_socket._closed:
                self.rtsp_socket.send(request.encode())
                response = self.rtsp_socket.recv(1024).decode()

                if "200 OK" in response:
                    self.text["text"] = "Teardown"
                    
                    # Close UDP socket only if it does exist
                    if self.udp_socket:
                        self.udp_socket.close()
                        self.udp_socket = None

                    # Reset state and variables
                    self.state = "INIT"
                    self.playing = False
                    self.paused = False
                    self.seq = 1
                    self.total_packets = 0
                    self.packets_lost = 0
                    self.packets_received = 0
                else:
                    self.text["text"] = "Teardown failed"
        except Exception as e:
            logger.error(f"Failed to send TEARDOWN request: {e}")
            self.text["text"] = f"Error TEARDOWN: {e}"

    def create_ui(self):
        self.root = Tk()
        self.root.wm_title("RTP Client")
        self.root.protocol("WM_DELETE_WINDOW", self.ui_close_window)

        # Create control buttons
        self.setup = self._create_button("Setup", self.ui_setup_event, 0, 0)
        self.start = self._create_button("Play", self.ui_play_event, 0, 1)
        self.pause = self._create_button("Pause", self.ui_pause_event, 0, 2)
        self.teardown = self._create_button("Teardown", self.ui_teardown_event, 0, 3)

        # Video
        self.movie = Label(self.root, height=29)
        self.movie.grid(row=1, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

        # Status and packets
        self.text = Label(self.root, height=3)
        self.text.grid(row=2, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
        self.counter = Label(self.root, height=2)
        self.counter.grid(row=3, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)

        return self.root

    def _create_button(self, text, command, row=0, column=0, width=20, padx=3, pady=3 ):
        button = Button(self.root, width=width, padx=padx, pady=pady)
        button["text"] = text
        button["command"] = command
        button.grid(row=row, column=column, padx=2, pady=2)
        return button

    def ui_close_window(self):

        """Clean up when closing UI window"""

        if self.state != "INIT":
            self.send_teardown_request()
        self.playing = False
        self.root.destroy()
        logger.debug("Window closed")
        sys.exit(0)

    # UI buttons handlers
    def ui_setup_event(self):

        """ Setup button handler """

        logger.debug("Setup button clicked")
        self.text["text"] = "Sending setup request..."
        self.send_setup_request()

    def ui_play_event(self):

        """ Play button handler """

        logger.debug("Play button clicked")
        self.text["text"] = "Sending play request..."
        self.send_play_request()

    def ui_pause_event(self):

        """ Pause button handler """

        logger.debug("Pause button clicked")
        self.text["text"] = "Sending pause request..."
        self.send_pause_request()

    def ui_teardown_event(self):

        """ Teardown button handler """

        logger.debug("Teardown button clicked")
        self.text["text"] = "Sending teardown request..."
        self.send_teardown_request()

    def updateMovie(self, data):
        photo = ImageTk.PhotoImage(Image.open(io.BytesIO(data)))
        self.movie.configure(image=photo, height=380) 
        self.movie.photo_image = photo
