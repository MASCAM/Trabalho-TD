from r2a.ir2a import IR2A
from player.parser import *
import time
import math
import numpy as np
import statistics as stats


class R2A_do_desespero(IR2A):

    def __init__(self, id):
        IR2A.__init__(self, id)
        self.throughputs = []
        self.time_of_download_per_segment = []
        self.segments_sizes = []
        self.avg_bandwidth = []
        self.buffer_size = []
        self.P = []
        self.kalman_gain = []
        self.kalman_filter = []
        self.buffer_size.append(0)
        self.avg_bandwidth.append(1000000)
        self.time_of_download_per_segment.append(0.5)
        self.segments_sizes.append(1000000)
        self.segments_sizes.append(0)
        self.max_buffer_size = self.whiteboard.get_max_buffer_size()
        self.request_time = 0
        self.qi = []
        self.minimum_buffersize = 5
        self.selected_index = 0
        self.last_index = 0
        self.gain = 1.0


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

        max_bit_rate = 5726737
        buffer = self.whiteboard.get_playback_buffer_size()
        
        if (len(buffer) > 0):
            actual_buffer_size = buffer[len(buffer) - 1][1]

        else:
            actual_buffer_size = 0



        self.buffer_size.append(actual_buffer_size)
        self.request_time = time.perf_counter()
        throughputs_top = self.throughputs.pop()
        if (throughputs_top > max_bit_rate):
            self.throughputs.append(4726737)

        else:
            self.throughputs.append(throughputs_top)

    
        #print(self.throughputs)
        #Melhor Resultado:
        #Pauses number: 6
        #>> Average Time Pauses: 2.02
        #>> Standard deviation: 1.57
        #>> Variance: 2.45
        #Average QI: 8.75
        #>> Standard deviation: 6.79
        #>> Variance: 46.1
        #Average QI distance: 2.34
        #>> Standard deviation: 5.26
        #>> Variance: 27.62
        #Parâmetros:
        #k = 0
        #a = 0
        #n = 10
        #max throughput length = 50, reduction of 30
        #BSlow = 5
        #selected Qi on BSlow = 0
        #if (len(self.throughputs) > 50):
        #    self.throughputs = self.throughputs[30:]
            
        variance = np.var(self.throughputs)
        std_error_of_the_mean = np.std(self.throughputs)
        std_deviation = std_error_of_the_mean
        if (len(self.throughputs) == 1):

            self.P.append(std_error_of_the_mean)
            self.kalman_filter.append(2500000)
            self.kalman_gain = [0.5]

        a = 0
        n = 15
        std_error_of_the_mean /= math.sqrt(len(self.throughputs))
        alfa = 0.9
        for i in range(0, len(self.throughputs)):
            
            if (i == 0):

                a = (1 - alfa) * self.throughputs[i]
                self.kalman_filter.append(a)     #se forem as primeiras posições n do vetor de entrada somente aplica 0 na saída

            else:

                a = alfa * self.kalman_filter[i - 1]       #caso contrário aplica a fórmula recursiva do filtro de média móvel ponderado exponencialmente demonstrado
                b = (1 - alfa) * self.throughputs[i - 1]
                self.kalman_filter.append(a + b)

        #print("Sinal Original: " + str(self.throughputs[len(self.throughputs) - 1]) + " Ganho de Kalmann: " + str(k) + " Sinal Filtrado: " + str(self.kalman_filter[len(self.kalman_filter) - 1]))
        avg = stats.mean(self.kalman_filter)
        self.avg_bandwidth.append(avg)  #acho que nem faz sentido
        #print(self.avg_bandwidth)
        selected_qi = self.qi[0]
        D = 0.0
        T = 0.0
        sum_D = 0.0
        sum_T = 0.0

        #print(actual_buffer_size)
        if ((actual_buffer_size > self.minimum_buffersize) and (len(self.throughputs) > n)):

            if (self.kalman_filter[len(self.kalman_filter) - 2] > self.kalman_filter[len(self.kalman_filter) - 1] and self.selected_index > 0 and self.buffer_size[len(self.buffer_size) - 1] + 10 <= self.max_buffer_size): #or (self.buffer_size[len(self.buffer_size) - 2] - self.buffer_size[len(self.buffer_size) - 1] >= self.minimum_buffersize)):

                self.gain *= 0.5
                self.avg_bandwidth[len(self.avg_bandwidth) - 1] *= self.gain
                    
            elif (self.buffer_size[len(self.buffer_size) - 1] > self.buffer_size[len(self.buffer_size) - 2] + 3 or self.buffer_size[len(self.buffer_size) - 1] + 10 > self.max_buffer_size): #or (self.buffer_size[len(self.buffer_size) - 2] <= self.buffer_size[len(self.buffer_size) - 1])):

                self.gain *= 2.0
                #
                self.avg_bandwidth[len(self.avg_bandwidth) - 1] *= self.gain

            if (self.selected_index == 0):

                self.gain = 1.0

            for i in range(len(self.throughputs) - n, len(self.throughputs)):

                #print(self.throughputs)
                #print(self.kalman_filter)
                #print(len(self.segments_sizes))
                #print(len(self.avg_bandwidth))
                #print(i)
                #print
                #if (buffer[len(buffer) - i - 2][1] > buffer[len(buffer) - i - 1][1]):

                    #print("Buffer anterior: " + str(buffer[len(buffer) - i - 2][1]) + " Buffer atual: " + str(buffer[len(buffer) - i - 1][1]))
                #    self.gain *= 0.5
                    

                #else:

                #    self.gain = self.gain * 1.8 if self.gain <= 1.0 else 1.0  
                #self.avg_bandwidth[i] *= self.gain
                T = self.segments_sizes[i] / self.avg_bandwidth[i]
                D = self.segments_sizes[i] #self.time_of_download_per_segment[i]
                sum_D += D
                sum_T += T
                #print(str(sum_T) + " " + str(actual_buffer_size))
                #print ("T: " + str(T) + " D: " + str(D) + " sum_T: " + str(sum_T) + " sum_D: " + str(sum_D))
                if (sum_T * self.minimum_buffersize > actual_buffer_size):

                    temp = sum_D / abs(sum_T - self.minimum_buffersize)
                    #print(str(max_bit_rate) + " " + str(temp))
                    if (temp < max_bit_rate):

                        max_bit_rate = temp


            for i in range(0, len(self.qi)):

                if max_bit_rate > self.qi[i]:

                    self.selected_index = i 

                else:

                    break

            if (actual_buffer_size  + 10 > self.max_buffer_size and self.selected_index == 0):

                self.selected_index = 10

            elif (self.selected_index >= 15 and actual_buffer_size <= 15):

                self.selected_index -= 5
                
            """
            elif (abs(self.selected_index - self.last_index) > 4 and self.selected_index > self.last_index):

                self.selected_index += 4

            elif (abs(self.selected_index - self.last_index) > 4 and self.selected_index < self.last_index):

                self.selected_index -= 4

            self.selected_index = 19 if self.selected_index > 19 else self.selected_index
            self.selected_index = 0 if self.selected_index < 0  else self.selected_index
            """
            selected_qi = self.qi[self.selected_index]
            self.last_index = self.selected_index
            

                

            """
            for i in range(0, len(self.qi)):
                if avg > self.qi[i]:             #15000
                    
                    self.selected_index = i
                    if ((kalman_filter[len(kalman_filter) - 1] - kalman_filter[len(kalman_filter) - 2] < 0) and self.selected_index > 0):
                        self.selected_index -= 1

                    selected_qi = self.qi[self.selected_index]     #16000
                    
                else:   
                    break
            """         

        #elif (actual_buffer_size > self.minimum_buffersize):
        #    selected_qi = self.qi[8]
        
        
        else:

            self.selected_index = 0
            selected_qi = self.qi[self.selected_index]
            self.last_index = self.selected_index
            """
            if (self.selected_index >= 3):
                self.selected_index -= 3

            else:
                self.selected_index = 0

            selected_qi = self.qi[self.selected_index]
            """
            
        msg.add_quality_id(selected_qi)
        self.send_down(msg)

    def handle_segment_size_response(self, msg):
        t = time.perf_counter() - self.request_time             #tempo que a mensagem demora pra voltar RTT
        #buffer = self.whiteboard.get_playback_buffer_size()
        #if (len(buffer) > 0):
        #    print('Time: ' + str(buffer[len(buffer) - 1][0]) + ' Buffer_size: ' + str(buffer[len(buffer) - 1][1]))

        #for i in buffer_time:
        #    print(i)
        bit_length = msg.get_bit_length()
        self.time_of_download_per_segment.append(t)
        self.segments_sizes.append(bit_length)
        self.throughputs.append(bit_length / t)      
        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass
