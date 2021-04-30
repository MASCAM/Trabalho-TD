#Trabalho realizado como parte da disciplina de Transmissão de Dados 2020/2
#Alunos:
#João Vítor Arantes Cabral - 17/0126048
#Leonardo Felipe de Oliveira - 17/0148751
#Gabriel Fernandes Carvalho - 17/0142698

from r2a.ir2a import IR2A
from player.parser import *
import time
import math
import numpy as np
import statistics as stats


class R2A_PID(IR2A):

    def __init__(self, id):
        IR2A.__init__(self, id)
        self.throughputs = []                               #vetor de vazões 
        self.segments_sizes = []                            #vetor do tamanho dos segmentos
        self.avg_bandwidth = []                             #vetor da média de vazões 
        self.buffer_size = []                               #vetor do tamanho do buffer
        self.biased_shifting_average_filter = []            #vetor do filtro de média móvel enviesada
        self.segments_sizes.append(2500000)                 #parâmetro definido como chute inicial
        self.max_buffer_size = self.whiteboard.get_max_buffer_size()
        self.request_time = 0
        self.qi = []
        self.minimum_buffersize = 3                         #definido empiricamente
        self.selected_index = 0                             #começa sempre na menor qualidade
        self.gain = 1.0                                     #ganho neutro 
        self.errors = []                                    #vetor de desvio padrão da média


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

        max_bit_rate = 4726737                                  #determina um teto para a taxa de bits, uma medida para 
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

        n = 10         #número de elementos pelos quais o filtro irá percorrer
        a = 0.0
        alfa = 0.7      #obtido empiricamente, muitos testes para determinar o mais adequado
        if (len(self.throughputs) > 50):    #para não virar um vetor muito grande

            self.throughputs = self.throughputs[-2 * n:]

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
        std_error_of_the_mean = np.std(self.biased_shifting_average_filter)/math.sqrt(n) #calcula o desvio padrão da média dos últimos n elementos filtrados
        error = std_error_of_the_mean / max_bit_rate  #esse erro é muito alto então se cria uma base para o erro para poder converte-lo para 
        self.errors.append(error)
        D = 0.0                                 #a mesma base dos índices de qualidade
        T = 0.0
        sum_D = 0.0
        sum_T = 0.0

        if (len(self.errors) > n):

            #2.0 0.8 0.02 foram os parâmetros determinados com a sintonia inicial
            #seleciona o ganho PID de acordo com a fórmula encontrada no slide em anexo do relatório
            proportional_gain = 2.0 * self.errors[-1]
            derivative_gain = 1.6 * (self.errors[-2] - self.errors[-1])/(self.segments_sizes[-1] / self.avg_bandwidth[-1])
            integrative_gain = 6.4 * np.sum(self.errors[-n:])
            self.gain = proportional_gain + derivative_gain + integrative_gain

    
        if ((actual_buffer_size > self.minimum_buffersize) and (len(self.throughputs) > n)):

            for i in range(len(self.throughputs) - n, len(self.throughputs)):
                #esse laço implementa o algoritmo 1 indicado no artigo 2 do relatório
                T = self.segments_sizes[i] / self.avg_bandwidth[i]*self.gain
                D = self.segments_sizes[i]
                sum_D += D
                sum_T += T
                if (sum_T > actual_buffer_size):

                    temp = sum_D / abs(sum_T - self.minimum_buffersize)
                    if (temp < max_bit_rate):

                        max_bit_rate = temp

            max_bit_rate *= abs(self.gain)
            for i in range(0, len(self.qi)):
                #seleciona o indice de qualidade correspondente ao bit rate ideal calculado
                if max_bit_rate > self.qi[i]:

                    self.selected_index = i 

                else:

                    break

            #print(self.gain) se quiser observar o ganho do sistema
            #a linha abaixo impede zeros no sistema (por conta do atraso aleatório no sinal)
            self.selected_index = self.buffer_size[len(self.buffer_size) - 1] - 2 if self.buffer_size[len(self.buffer_size) - 1] <= self.selected_index else self.selected_index
            #as duas linhas abaixo impedem índices inválidos
            self.selected_index = 19 if self.selected_index > 19 else self.selected_index
            self.selected_index = 0 if self.selected_index < 0  else self.selected_index
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
