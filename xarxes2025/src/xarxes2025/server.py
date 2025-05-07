import socket
import threading
import time

from loguru import logger
from xarxes2025.udpdatagram import UDPDatagram
from xarxes2025.videoprocessor import VideoProcessor


class ClientSession(threading.Thread):
    def __init__(self, client_socket, client_address, server_config):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.client_address = client_address
        self.host, self.port, self.max_frames, self.frame_rate, self.loss_rate, self.error = server_config

        self.sessionid = f"XARXES{self.client_address[1]}"
        self.client_udp_port = None
        self.udp_socket = None
        self.video = None
        self.state = "INIT"
        self.streaming = threading.Event()
        self.paused_event = threading.Event()

    def run(self):
        try:
            while True:
                data = self.client_socket.recv(1024).decode()
                if not data:
                    logger.info(f"Client {self.client_address} disconnected")
                    break

                logger.debug(f"Received from client {self.client_address}:\n{data}")
                if data.startswith("SETUP"):
                    logger.error(f"{data}")
                    self.handle_setup(data)
                elif data.startswith("PLAY"):
                    self.handle_play(data)
                elif data.startswith("PAUSE"):
                    self.handle_pause(data)
                elif data.startswith("TEARDOWN"):
                    self.handle_teardown(data)
                    
        except Exception as e:
            logger.error(f"Error handling client {self.client_address}: {e}")

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
                    self.udp_socket.sendto(datagram, (self.client_address[0], self.client_udp_port))
                    logger.debug(f"Sent frame {self.video.get_frame_number()} to {self.client_address}")
                    time.sleep(1 / self.frame_rate)
                else:
                    logger.info(f"No more frames to send to {self.client_address}")
                    break
        except Exception as e:
            logger.error(f"Error in UDP streaming: {e}")

    def handle_setup(self, data):
    # Bloquejar SETUP si no estem a INIT
        if self.state != "INIT":
            logger.warning(f"SETUP ignored: current state is {self.state}")
            cseq_value = self.get_cseq(data)
            response = (
                f"RTSP/1.0 400 Method Not Valid in This State\r\n"
                f"CSeq: {cseq_value}\r\n"
                f"Session: {self.sessionid}\r\n"
            )
            self.client_socket.send(response.encode())
            return


        cseq_value = self.get_cseq(data)
        filename = data.split(" ")[1].strip() if len(data.split(" ")) >= 2 else "rick.webm"
        self.client_udp_port = self.extract_udp_port(data)
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            self.video = VideoProcessor(filename)
            logger.info(f"Video loaded: {filename}")
        except Exception as e:
            logger.error(f"Failed to load video: {e}")
            return

        self.state = "READY"
        self.paused_event.clear()

        response = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: {cseq_value}\r\n"
            f"Session: {self.sessionid}\r\n"
        )
        self.client_socket.send(response.encode())
        logger.debug(f"Sent SETUP OK to {self.client_address}")


    def handle_play(self, data):
        cseq_value = self.get_cseq(data)
        self.paused_event.clear()

        response = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: {cseq_value}\r\n"
            f"Session: {self.sessionid}\r\n"
        )
        self.client_socket.send(response.encode())
        logger.debug(f"Sent PLAY OK to {self.client_address}")
        self.state = "PLAYING"

        if not self.streaming.is_set():
            threading.Thread(target=self.start_streaming_udp, daemon=True).start()

    def handle_pause(self, data):
        cseq_value = self.get_cseq(data)
        self.paused_event.set()

        response = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: {cseq_value}\r\n"
            f"Session: {self.sessionid}\r\n"
        )
        self.client_socket.send(response.encode())
        logger.debug(f"Sent PAUSE OK to {self.client_address}")
        self.state = "READY"

    def handle_teardown(self, data):
        cseq_value = self.get_cseq(data)

        response = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: {cseq_value}\r\n"
            f"Session: {self.sessionid}\r\n"
        )
        self.client_socket.send(response.encode())
        logger.debug(f"Sent TEARDOWN OK to {self.client_address}")

        self.streaming.clear()
        self.paused_event.clear()
        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None
        
        self.state = "INIT"
        self.video = None

    def get_cseq(self, data):
        for line in data.split("\n"):
            if line.startswith("CSeq"):
                return line.split(":")[1].strip()
        return "0"


class Server(object):
    def __init__(self, port, host, max_frames, frame_rate, loss_rate, error):
        self.host = host
        self.port = port
        self.max_frames = max_frames
        self.frame_rate = frame_rate
        self.loss_rate = loss_rate
        self.error = error
        self.running = True

        logger.debug(f"Server created")
        self.start_tcp_server()

    def start_tcp_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        logger.info(f"RTSP Server listening on {self.host}:{self.port}")

        try:
            while self.running:
                client_socket, client_address = self.server_socket.accept()
                logger.info(f"New client connected from {client_address}")
                session = ClientSession(
                    client_socket,
                    client_address,
                    (self.host, self.port, self.max_frames, self.frame_rate, self.loss_rate, self.error)
                )
                session.start()
        except KeyboardInterrupt:
            logger.warning("Server interrupted by user")
        finally:
            self.server_socket.close()
            logger.info("Server shutdown")
