from loguru import logger
# from xarxes2025.udpdatagram import UDPDatagram
# from xarxes2025.videoprocessor import VideoProcessor


class Server(object):
    def __init__(self, port, host = "127.0.0.1", max_frames = None, frame_rate = 25, loss_rate = 0, error = 0):       
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
        self.server_socket = socket.socket(socket.AF_INET, socket. SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        logger.info(f"RTSP Server listening on {self.host}:{self.port}")

        try:
            while self.running:
                client_socket, client_address = self.server_socket.accept()
                logger.info(f"New client connected from {client_address}")
                threading.Thread(target = self.handle_client, args = (client_socket, client_address)).start()
        except KeyboardInterrupt:
            logger.warning("Server interrupted by user")
        finally:
            self.server_socket.close()
            logger.info("Server shut down")

    def handle_client(self, client_socket, client_address):
        logger.debug(f"Handling client")
        client_socket.close()

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
                        
