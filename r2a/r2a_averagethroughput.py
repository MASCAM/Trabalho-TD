from r2a.ir2a import IR2A
from player.parser import *
import time
from statistics import mean


class R2A_AverageThroughput(IR2A):

    def __init__(self, id):
        IR2A.__init__(self, id)
        self.throughputs = []
        self.request_time = 0
        self.qi = []

    def handle_xml_request(self, msg):
        self.request_time = time.perf_counter()
        self.send_down(msg)

    def handle_xml_response(self, msg):

        parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = parsed_mpd.get_qi()

        t = time.perf_counter() - self.request_time
        self.throughputs.append(msg.get_bit_length() / t)

        self.send_up(msg)

    def handle_segment_size_request(self, msg):
        self.request_time = time.perf_counter()
        avg = mean(self.throughputs) / 2        #16000

        selected_qi = self.qi[0]
        for i in self.qi:
            if avg > i:             #15000
                selected_qi = i     #16000

            else:   
                break

        msg.add_quality_id(selected_qi)
        self.send_down(msg)

    def handle_segment_size_response(self, msg):
        t = time.perf_counter() - self.request_time             #tempo que a mensagem demora pra voltar RTT
        self.throughputs.append(msg.get_bit_length() / t)       #[0 10 11 21 21 21 30 30 30 30 25 23]
        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass
