import socket
import threading
import time
import io

from loguru import logger
from xarxes2025.udpdatagram import UDPDatagram
from xarxes2025.videoprocessor import VideoProcessor


class Server(object):
    def __init__(self, port, host, max_frames, frame_rate, loss_rate, error):
        self.host = host
        self.port = port
        self.max_frames = max_frames
        self.frame_rate = frame_rate
        self.loss_rate = loss_rate
        self.error = error
        self.running = True
        self.state = "INIT"
        self.streaming_thread = None
        self.client_udp_port = None
        self.client_address = None
        self.video = None
        self.streaming = threading.Event()
        self.paused_event = threading.Event()  # nuevo control de pausa
        self.udp_socket = None

        logger.debug(f"Server created")
        self.start_tcp_server()

    def extract_udp_port(self, request_data):
        for line in request_data.split("\n"):
            if "Transport" in line:
                parts = line.split(";")
                for part in parts:
                    if "client_port" in part:
                        return int(part.split("=")[1])
        return 25000

    def start_streaming_udp(self):
        self.streaming.set()
        try:
            while self.streaming.is_set():
                if self.paused_event.is_set():
                    time.sleep(0.1)
                    continue

                frame_data = self.video.next_frame()
                if frame_data:
                    datagram = UDPDatagram(self.video.get_frame_number(), frame_data).get_datagram()
                    self.udp_socket.sendto(datagram, (self.client_address, self.client_udp_port))
                    logger.debug(f"Sent frame {self.video.get_frame_number()}")
                    time.sleep(1 / self.frame_rate)
                else:
                    logger.info("No more frames to send")
                    break
        except Exception as e:
            logger.error(f"Error in UDP streaming: {e}")

    def start_tcp_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        logger.info(f"RTSP Server listening on {self.host}:{self.port}")

        try:
            while self.running:
                client_socket, client_address = self.server_socket.accept()
                logger.info(f"New client connected from {client_address}")
                threading.Thread(target=self.handle_client, args=(client_socket, client_address)).start()
        except KeyboardInterrupt:
            logger.warning("Server interrupted by user")

    def handle_client(self, client_socket, client_address):
        logger.debug(f"Handling client {client_address}")
        try:
            while True:
                data = client_socket.recv(1024).decode()
                if not data:
                    logger.info(f"Client {client_address} disconnected")
                    break

                logger.debug(f"Received from client:\n{data}")

                if data.startswith("SETUP"):
                    self.handle_setup(data, client_socket, client_address)
                elif data.startswith("PLAY"):
                    self.handle_play(data, client_socket)
                elif data.startswith("PAUSE"):
                    self.handle_pause(data, client_socket)
                elif data.startswith("TEARDOWN"):
                    self.handle_teardown(data, client_socket)
        except Exception as e:
            logger.error(f"Error handling client {client_address}: {e}")

    def handle_setup(self, data, client_socket, client_address):
        cseq_value = self.get_cseq(data)
        session_id = "XARXES_00005017"
        self.filename = data.split(" ")[1].strip() if len(data.split(" ")) >= 2 else "rick.webm"
        self.client_address = client_address[0]
        self.client_udp_port = self.extract_udp_port(data)
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        if self.video is None:
            try:
                self.video = VideoProcessor(self.filename)
                logger.info(f"Video loaded: {self.filename}")
            except Exception as e:
                logger.error(f"Failed to load video: {e}")
                return

        self.state = "READY"
        self.paused_event.clear()

        response = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: {cseq_value}\r\n"
            f"Session: {session_id}\r\n"
        )
        client_socket.send(response.encode())
        logger.debug(f"Sent SETUP OK")

    def handle_play(self, data, client_socket):
        cseq_value = self.get_cseq(data)
        self.paused_event.clear()

        response = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: {cseq_value}\r\n"
            f"Session: XARXES_00005017\r\n"
        )
        client_socket.send(response.encode())
        logger.debug(f"Sent PLAY OK")

        if not self.streaming_thread or not self.streaming_thread.is_alive():
            self.streaming.set()
            self.streaming_thread = threading.Thread(target=self.start_streaming_udp)
            self.streaming_thread.start()

    def handle_pause(self, data, client_socket):
        cseq_value = self.get_cseq(data)
        self.paused_event.set()

        response = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: {cseq_value}\r\n"
            f"Session: XARXES_00005017\r\n"
        )
        client_socket.send(response.encode())
        logger.debug("Sent PAUSE OK")

    def handle_teardown(self, data, client_socket):
        cseq_value = self.get_cseq(data)

        response = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: {cseq_value}\r\n"
            f"Session: XARXES_00005017\r\n"
        )
        client_socket.send(response.encode())
        logger.debug(f"Sent TEARDOWN OK")

        self.streaming.clear()
        self.paused_event.clear()
        if self.streaming_thread and self.streaming_thread.is_alive():
            self.streaming_thread.join()

        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None

        self.video = None

    def get_cseq(self, data):
        for line in data.split("\n"):
            if line.startswith("CSeq"):
                return line.split(":")[1].strip()
        return "0"

    def send_udp_frame(self):
        if not self.video or not self.udp_socket:
            logger.warning("UDP socket or video not initialized.")

        frame_data = self.video.next_frame()
        if frame_data:
            frame_number = self.video.get_frame_number()
            udp_datagram = UDPDatagram(frame_number, frame_data).get_datagram()
            self.udp_socket.sendto(udp_datagram, (self.client_address, self.client_udp_port))
            logger.debug(f"Sent frame {frame_number} via send_udp_frame")
        else:
            logger.info("No more frames to send in send_udp_frame")
