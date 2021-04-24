from r2a.ir2a import IR2A
from player.parser import *
import time
import math
import numpy as np
import statistics as stats


class R2A_PID(IR2A):

    def __init__(self, id):
        IR2A.__init__(self, id)
        self.throughputs = []
        self.segments_sizes = []
        self.avg_bandwidth = []
        self.buffer_size = []
        self.biased_shifting_average_filter = []
        self.biased_shifting_average_filter.append(2500000) #parâmetros definidos inicialmente como 
        self.buffer_size.append(0)                          #um chute inicial para as estimativas
        self.avg_bandwidth.append(1000000)                  #lembrando que o throughput começa já com um elemento no vetor
        self.segments_sizes.append(1000000)                 #por isso essas inicializações aqui
        self.max_buffer_size = self.whiteboard.get_max_buffer_size()
        self.request_time = 0
        self.qi = []
        self.minimum_buffersize = 5                         #definido empiricamente
        self.selected_index = 0                             #começa sempre na menor qualidade
        self.gain = 1.0                                     #ganho neutro 


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

        max_bit_rate = 5726737                                  #determina um teto para a taxa de bits, uma medida para 
        buffer = self.whiteboard.get_playback_buffer_size()     #diminuir o ruído do sinal de entrada logo de cara
        if (len(buffer) > 0):                                   #afinal a maxima taxa de bits é 4726737 
            actual_buffer_size = buffer[len(buffer) - 1][1]

        else:
            actual_buffer_size = 0

        self.request_time = time.perf_counter()
        self.buffer_size.append(actual_buffer_size)             #após obter o tamanho do buffer atual, o "empilha"
        throughputs_top = self.throughputs.pop()
        if (throughputs_top > max_bit_rate):

            self.throughputs.append(4726737)                    #como dito, medida para amenizar topos

        else:
            
            self.throughputs.append(throughputs_top)

        n = 10          #número de elementos pelos quais o filtro irá percorrer
        a = 0
        alfa = 0.7      #obtido empiricamente, muitos testes para determinar o mais adequado
        for i in range(0, len(self.throughputs)):   #filtra o sinal de entrada
            
            if (i == 0):

                a = (1 - alfa) * self.throughputs[i]
                self.biased_shifting_average_filter.append(a)     #se forem as primeiras posições n do vetor de entrada somente aplica 0 na saída

            else:

                a = alfa * self.biased_shifting_average_filter[i - 1]       #caso contrário aplica a fórmula recursiva do filtro de média móvel ponderado exponencialmente demonstrado
                b = (1 - alfa) * self.throughputs[i - 1]
                self.biased_shifting_average_filter.append(a + b)           #fórmula descrita no relatório
        
        avg = self.biased_shifting_average_filter[len(self.biased_shifting_average_filter) - 1] #vazão filtrada como estimativa de banda
        self.avg_bandwidth.append(avg)  
        std_error_of_the_mean = np.std(self.biased_shifting_average_filter[-n:])/math.sqrt(n) #calcula o desvio padrão da média dos últimos n elementos filtrados
        error = std_error_of_the_mean / 46980   #esse erro é muito alto então se cria uma base para o erro para poder converte-lo para 
        D = 0.0                                 #a mesma base dos índices de qualidade
        T = 0.0
        sum_D = 0.0
        sum_T = 0.0

        if ((actual_buffer_size > self.minimum_buffersize) and (len(self.throughputs) > n)):

            if (self.biased_shifting_average_filter[len(self.biased_shifting_average_filter) - 2] > self.biased_shifting_average_filter[len(self.biased_shifting_average_filter) - 1] and self.selected_index > 0 and self.buffer_size[len(self.buffer_size) - 1] + 10 <= self.max_buffer_size): #or (self.buffer_size[len(self.buffer_size) - 2] - self.buffer_size[len(self.buffer_size) - 1] >= self.minimum_buffersize)):
                #de certa forma como ambos sinal filtrado
                self.gain *= 0.5
                self.avg_bandwidth[len(self.avg_bandwidth) - 1] *= self.gain
                    
            elif (self.buffer_size[len(self.buffer_size) - 1] > self.buffer_size[len(self.buffer_size) - 2] + 3 or self.buffer_size[len(self.buffer_size) - 1] + 10 > self.max_buffer_size): 
                #e buffer size se alteram somente quando há inconstâncias no sinal de entrada
                self.gain = 2.0
                self.avg_bandwidth[len(self.avg_bandwidth) - 1] *= self.gain
                #pode-se dizer que o ganho padrão do sistema está sendo modelado pelo erro
            if (self.selected_index == 0):  #evita que o sistema fique preso em um zero

                self.gain = 1.0
            #todos os parâmetros do bloco de comparações acima foram determinados empiricamente
            for i in range(len(self.throughputs) - n, len(self.throughputs)):
                #esse laço implementa o algoritmo 1 indicado no artigo 2 do relatório
                T = self.segments_sizes[i] / self.avg_bandwidth[i]
                D = self.segments_sizes[i]
                sum_D += D
                sum_T += T
                if (sum_T * self.minimum_buffersize > actual_buffer_size):

                    temp = sum_D / abs(sum_T - self.minimum_buffersize)
                    if (temp < max_bit_rate):

                        max_bit_rate = temp


            for i in range(0, len(self.qi)):
                #seleciona o indice de qualidade correspondente ao bit rate ideal calculado
                if max_bit_rate > self.qi[i]:

                    self.selected_index = i 

                else:

                    break
            #bloco mais importante do sistema de controle e que foi todo definido empiricamente, tentativa e erro
            if (actual_buffer_size  >= 18 and self.selected_index == 0):
            #impede que o buffer size exploda pra cima
                self.selected_index = 10

            elif (self.selected_index >= 15 and actual_buffer_size <= 18 and error >= 1.0):
            #se o buffer size está pequeno para um index de qualidade tão alto, tendo um erro significativo
                self.selected_index -= math.floor(5 * math.sqrt(error)) #diminui o índice
                
            elif (self.selected_index <= 10 and actual_buffer_size >= 15 and error >= 1.0):
            #o contrário do caso acima
                self.selected_index += math.floor(5 * math.sqrt(error))

            elif (actual_buffer_size + 10 >= self.max_buffer_size):
            #impede o overflow do buffer
                self.selected_index += 3
            #as duas linhas abaixo impedem índices inválidos
            self.selected_index = 19 if self.selected_index > 19 else self.selected_index
            self.selected_index = 0 if self.selected_index < 0  else self.selected_index
            self.selected_index = self.buffer_size[len(self.buffer_size) - 1] - 3 if self.buffer_size[len(self.buffer_size) - 1] <= self.selected_index else self.selected_index
            #a linha acima impede que um índice escolhido seja maior do que o buffer size
            selected_qi = self.qi[self.selected_index]
        
        else:
            #serve de inicialização, são selecionados N índices iguais a 0 no início da execução
            #meio inconveniente mas tem tudo a ver com o atraso inicial do sinal
            self.selected_index = 0
            selected_qi = self.qi[self.selected_index]
            #é desejável cair o menor número de vezes possível nesse caso e ao mesmo tempo
            #ter um controle razoável da qualidade e do buffer size IMPEDINDO PAUSAS
        msg.add_quality_id(selected_qi)
        self.send_down(msg)

    def handle_segment_size_response(self, msg):

        t = time.perf_counter() - self.request_time #a base utilizada inicialmente foi sim o R2A de média
        bit_length = msg.get_bit_length()
        self.segments_sizes.append(bit_length)
        self.throughputs.append(bit_length / t)      
        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass
