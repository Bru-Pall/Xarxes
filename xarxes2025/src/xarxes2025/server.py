import socket
import threading

from loguru import logger
# from xarxes2025.udpdatagram import UDPDatagram
# from xarxes2025.videoprocessor import VideoProcessor


class Server(object):
    def __init__(self, port, host , max_frames, frame_rate , loss_rate , error):       
        """
        Initialize a new VideoStreaming server.

        :param port: The port to listen on.
        """
        self.host = host
        self.port = port
        self.max_frames = max_frames
        self.loss_rate = loss_rate
        self.error = error
        self.running = True

        logger.debug(f"Server created ")
        self.start_tcp_server()
    def start_tcp_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        logger.info(f"RTSP Server listening on {self.host}:{self.port}")

        try:
            while self.running:
                client_socket, client_address = self.server_socket.accept()
                logger.error(f"New client connected from {client_address}")
                threading.Thread(target = self.handle_client, args = (client_socket, client_address)).start()
        except KeyboardInterrupt:
            logger.warning("Server interrupted by user")
        finally:
            self.server_socket.close()
            logger.info("Server shut down")

    def handle_client(self, client_socket, client_address):
        logger.debug(f"Handling client")
        try:
            data = client_socket.recv(1024).decode()
            logger.debug(f"Recieved from client")

            if data.startswith("SETUP"):
                cseq_line = [line for line in data.split("\n") if line.startswith("CSeq")][0]
                cseq_value = cseq_line.split(":")[1].strip()

                session_id = "XARXES_00005017"

                if self.error == 1:
                    response = f"RTSP/1.0 400 Bad Request\r\nCSeq"
                elif self.error == 2:
                    response = f"RTSP/1.0 500 Internal Server Error\r\nCSeq"
                else:
                    response = (
                        f"RTSP/1.0 200 OK\r\n"
                        f"CSeq: {cseq_value}\r\n"
                        f"Session: {session_id}\r\n"
                        f"\r\n"
                    )
                
                logger.error(f"Sending response to client :\n {response}")
                client_socket.send(response.encode())
        
        except Exception as e:
            logger.error(f"Error handling client")
        finally:
            client_socket.close()
            logger.info(f"Connections with client closed")

    # # 
    # # This is not complete code, it's just an skeleton to help you get started.
    # # You will need to use these snippets to do the code.
    # # 
    # #     
    # def send_udp_frame(self):
      
    #     # This snippet reads from self.video (a VideoProcessor object) and prepares 
    #     # the frame to be sent over UDP. 

    #     data = self.video.next_frame()
    #     if data:
    #         if len(data)>0:
    #                 frame_number = self.get_frame_number()
    #                 # create UDP Datagram

    #                 udp_datagram = UDPDatagram(frame_number, data).get_datagram()

    #                 # send UDP Datagram
    #                 socketudp.sendto(udp_datagram, (address, port))
                        
