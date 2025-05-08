import socket
import threading
import time
import random

from loguru import logger
from xarxes2025.udpdatagram import UDPDatagram
from xarxes2025.videoprocessor import VideoProcessor

# RTSP status codes to eith their messages
RTSP_STATUS_MESSAGES = {
    200: "OK",
    400: "Bad Request",
    404: "File Not Found",
    500: "Internal Server Error",
    501: "Not Implemented"
}

def build_rtsp_response(status_code, cseq, session_id):

    """ Build RTSP response messages """

    message = RTSP_STATUS_MESSAGES.get(status_code, "Unknown")
    return (
        f"RTSP/1.0 {status_code} {message}\r\n"
        f"CSeq: {cseq}\r\n"
        f"Session: {session_id}\r\n"
    )

class ClientSession(threading.Thread):
    def __init__(self, client_socket, client_address, server_config):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.client_address = client_address
        self.host, self.port, self.max_frames, self.frame_rate, self.loss_rate, self.error = server_config

        # Unique session ID
        self.sessionid = f"XARXES{self.client_address[1]}"

        self.client_udp_port = None
        self.udp_socket = None
        self.video = None
        self.state = "INIT"

        # Thread control events
        self.streaming = threading.Event()
        self.paused_event = threading.Event()

    def run(self):

        """ Main thread loop handling RTSP requests """

        try:
            while True:
                data = self.client_socket.recv(1024).decode()
                if not data:
                    break

                # Route to the appropiate handler
                if data.startswith("SETUP"):
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

        """ Extrcat client's UDP port from Setup request's transport header or return default """

        for line in request_data.split("\n"):
            if "Transport" in line:
                parts = line.split(";")
                for part in parts:
                    if "client_port" in part:
                        return int(part.split("=")[1])
        return 25000

    def start_streaming_udp(self):

        """ Main video streaming loop running in a separate thread """

        self.streaming.set()
        frame_count = 0
        try:
            while self.should_continue_streaming(frame_count):
                frame_data = self.get_next_frame()

                # When paused
                if frame_data is None:
                    continue

                if self.process_frame(frame_data):
                    frame_count += 1
                time.sleep(1 / self.frame_rate)

        except Exception as e:
            logger.error(f"Error in UDP streaming: {e}")

    def should_continue_streaming(self, frame_count):

        """ Check if streaming should continue based on state frame count """

        return self.streaming.is_set() and not self.reached_max_frames(frame_count)

    def get_next_frame(self):

        """ Get next video frame """

        if self.paused_event.is_set():
            time.sleep(0.1)
            return None
        return self.video.next_frame()

    def process_frame(self, frame_data):

        """ Process and send a frame with optional packet loss simulation """

        if frame_data and not self.should_drop_packet():

            # Create UDP datagram and send to client
            datagram = UDPDatagram(self.video.get_frame_number(), frame_data).get_datagram()
            self.udp_socket.sendto(datagram, (self.client_address[0], self.client_udp_port))
            return True
        return False

    def should_drop_packet(self):

        """ Simulate network packet loss based on configured rate """

        return random.randint(1, 100) <= self.loss_rate

    def reached_max_frames(self, count):

        """ Check if maximum frame count has been reached """

        return self.max_frames > 0 and count >= self.max_frames

    def handle_setup(self, data):

        """ Handle Setup request to initialize streaming session """

        cseq_value = self.get_cseq(data)
        
        # VAlidate state
        if self.state != "INIT":
            response = build_rtsp_response(400, cseq_value, self.sessionid)
            self.client_socket.send(response.encode())
            return

        # Extract filename from request
        filename = data.split(" ")[1].strip() if len(data.split(" ")) >= 2 else "rick.webm"

        # Get client's UDP port and create UDP socket
        self.client_udp_port = self.extract_udp_port(data)
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            # Initialize video processor
            self.video = VideoProcessor(filename)
        except Exception as e:
            logger.error(f"Failed to load video: {e}")
            response = build_rtsp_response(404, cseq_value, self.sessionid)
            self.client_socket.send(response.encode())
            return

        # Update state and send succes response
        self.state = "READY"
        self.paused_event.clear()
        response = build_rtsp_response(200, cseq_value, self.sessionid)
        self.client_socket.send(response.encode())

    def handle_play(self, data):

        """ Handle Play request to start or resume streaming """

        cseq_value = self.get_cseq(data)
        self.paused_event.clear()

        # Send response and update state
        response = build_rtsp_response(200, cseq_value, self.sessionid)
        self.client_socket.send(response.encode())
        self.state = "PLAYING"

        # Start streaming thread if not already running
        if not self.streaming.is_set():
            threading.Thread(target=self.start_streaming_udp, daemon=True).start()

    def handle_pause(self, data):

        """ Handle Pause request to temporarily stop streaming """

        cseq_value = self.get_cseq(data)
        self.paused_event.set()

        # Send response and update state
        response = build_rtsp_response(200, cseq_value, self.sessionid)
        self.client_socket.send(response.encode())
        self.state = "READY"

    def handle_teardown(self, data):

        """ Handle Teardown request to end session """

        cseq_value = self.get_cseq(data)

        # Send response
        response = build_rtsp_response(200, cseq_value, self.sessionid)
        self.client_socket.send(response.encode())

        # Clean up resources
        self.streaming.clear()
        self.paused_event.clear()
        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None

        # Reset state
        self.state = "INIT"
        self.video = None

    def get_cseq(self, data):

        """ Extract CSeq number from RTSP request """

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

        self.start_tcp_server()

    def start_tcp_server(self):

        """ Main server loop accepting client connections """

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)

        try:
            while self.running:
                # Accept new client connection
                client_socket, client_address = self.server_socket.accept()

                # Create and start client session thread
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
