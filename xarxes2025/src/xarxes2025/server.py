import socket
import threading
import time
import io

from loguru import logger
from xarxes2025.udpdatagram import UDPDatagram
from xarxes2025.videoprocessor import VideoProcessor


class Server(object):
    def __init__(self, port, host, max_frames, frame_rate, loss_rate, error):
        """Initialize a new VideoStreaming server."""
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
        self.paused = False
        self.streaming = False

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
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logger.info(f"Starting UDP streaming to {self.client_address}:{self.client_udp_port}")
        self.streaming = True
        try:
            while self.streaming:
                if self.paused:
                    time.sleep(0.1)
                    continue

                frame_data = self.video.next_frame()
                if frame_data:
                    datagram = UDPDatagram(self.video.get_frame_number(), frame_data).get_datagram()
                    udp_socket.sendto(datagram, (self.client_address, self.client_udp_port))
                    logger.debug(f"Sent frame {self.video.get_frame_number()}")
                    time.sleep(1 / self.frame_rate)
                else:
                    logger.info("No more frames to send")
                    break
        except Exception as e:
            logger.error(f"Error in UDP streaming: {e}")
        finally:
            udp_socket.close()
            self.streaming = False
            logger.info("Stopped UDP streaming")

    def start_tcp_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        logger.info(f"RTSP Server listening on {self.host}:{self.port}")

        try:
            while self.running:
                client_socket, client_address = self.server_socket.accept()
                logger.error(f"New client connected from {client_address}")
                threading.Thread(target=self.handle_client, args=(client_socket, client_address)).start()
        except KeyboardInterrupt:
            logger.warning("Server interrupted by user")
        finally:
            self.server_socket.close()
            logger.info("Server shut down")

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
                    cseq_line = [line for line in data.split("\n") if line.startswith("CSeq")][0]
                    cseq_value = cseq_line.split(":")[1].strip()

                    session_id = "XARXES_00005017"
                    first_line = data.split("\n")[0]
                    parts = first_line.split(" ")
                    self.filename = parts[1].strip() if len(parts) >= 2 else "rick.webm"
                    self.client_address = client_address[0]
                    self.client_udp_port = self.extract_udp_port(data)

                    try:
                        self.video = VideoProcessor(self.filename)
                        logger.info(f"Video loaded: {self.filename}")
                    except Exception as e:
                        logger.error(f"Failed to load video: {e}")
                        return

                    self.state = "READY"
                    self.paused = False

                    response = (
                        f"RTSP/1.0 200 OK\r\n"
                        f"CSeq: {cseq_value}\r\n"
                        f"Session: {session_id}\r\n"
                        f"\r\n"
                    )
                    client_socket.send(response.encode())
                    logger.debug(f"Sent SETUP OK")

                elif data.startswith("PLAY"):
                    cseq_line = [line for line in data.split("\n") if line.startswith("CSeq")][0]
                    cseq_value = cseq_line.split(":")[1].strip()

                    response = (
                        f"RTSP/1.0 200 OK\r\n"
                        f"CSeq: {cseq_value}\r\n"
                        f"Session: XARXES_00005017\r\n"
                        f"\r\n"
                    )
                    client_socket.send(response.encode())
                    logger.debug(f"Sent PLAY OK")

                    self.paused = False
                    if not self.streaming_thread or not self.streaming_thread.is_alive():
                        threading.Thread(target=self.start_streaming_udp).start()

                elif data.startswith("PAUSE"):
                    cseq_line = [line for line in data.split("\n") if line.startswith("CSeq")][0]
                    cseq_value = cseq_line.split(":")[1].strip()

                    self.paused = True

                    response = (
                        f"RTSP/1.0 200 OK\r\n"
                        f"CSeq: {cseq_value}\r\n"
                        f"Session: XARXES_00005017\r\n"
                        f"\r\n"
                    )
                    client_socket.send(response.encode())
                    logger.debug("Sent PAUSE OK")

                elif data.startswith("TEARDOWN"):
                    cseq_line = [line for line in data.split("\n") if line.startswith("CSeq")][0]
                    cseq_value = cseq_line.split(":")[1].strip()

                    response = (
                        f"RTSP/1.0 200 OK\r\n"
                        f"CSeq: {cseq_value}\r\n"
                        f"Session: XARXES_00005017\r\n"
                        f"\r\n"
                    )
                    client_socket.send(response.encode())
                    logger.debug(f"Sent TEARDOWN OK")

                    self.running = False
                    break

        except Exception as e:
            logger.error(f"Error handling client {client_address}: {e}")
        finally:
            client_socket.close()
            logger.info(f"Connection with {client_address} closed")

    def send_udp_frame(self):
        data = self.video.next_frame()
        if data and len(data) > 0:
            frame_number = self.get_frame_number()
            udp_datagram = UDPDatagram(frame_number, data).get_datagram()
            socketudp.sendto(udp_datagram, (address, port))
