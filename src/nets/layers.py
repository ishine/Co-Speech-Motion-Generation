import os
import sys
sys.path.append(os.getcwd())

import torch
import torch.nn as nn
import numpy as np
from nets.graph_definition import *


def get_log(x):
    log=0
    while x>1:
        if x%2 == 0:
            x = x // 2
            log += 1
        else:
            raise ValueError('x is not a power of 2')

    return log

class ConvNormRelu(nn.Module):
    '''
    (B,C_in,H,W) -> (B, C_out, H, W) 
    存在一些kernel size的选择会导致输出不是H/s
    '''
    def __init__(self, 
                    in_channels, 
                    out_channels,
                    type='1d', 
                    leaky=False,
                    downsample=False, 
                    kernel_size=None, 
                    stride=None,
                    padding=None, 
                    p=0, 
                    groups=1,
                    residual=False):
        '''
        简单的conv-bn-relu
        '''
        super(ConvNormRelu, self).__init__()
        self.residual = residual

        if kernel_size is None and stride is None:
            if not downsample:
                kernel_size = 3
                stride = 1
            else:
                kernel_size = 4 
                stride = 2
        
        if padding is None:
            if isinstance(kernel_size, int) and isinstance(stride, tuple):
                padding = tuple(int((kernel_size - st)/2) for st in stride)
            elif isinstance(kernel_size, tuple) and isinstance(stride, int):
                padding = tuple(int((ks - stride)/2) for ks in kernel_size)
            elif isinstance(kernel_size, tuple) and isinstance(stride, tuple):
                padding = tuple(int((ks - st)/2) for ks, st in zip(kernel_size, stride))
            else:
                padding = int((kernel_size - stride)/2)

        
        if self.residual:
            if downsample:
                if type == '1d':
                    self.residual_layer = nn.Sequential(
                        nn.Conv1d(
                            in_channels=in_channels,
                            out_channels=out_channels,
                            kernel_size=kernel_size,
                            stride=stride,
                            padding=padding
                        )
                    )
                elif type == '2d':
                    self.residual_layer = nn.Sequential(
                        nn.Conv2d(
                            in_channels=in_channels,
                            out_channels=out_channels,
                            kernel_size=kernel_size,
                            stride=stride,
                            padding=padding
                        )
                    )
            else:
                if in_channels == out_channels:
                    self.residual_layer = nn.Identity()
                else:
                    if type == '1d':
                        self.residual_layer = nn.Sequential(
                            nn.Conv1d(
                                in_channels=in_channels,
                                out_channels=out_channels,
                                kernel_size=kernel_size,
                                stride=stride,
                                padding=padding
                            )
                        )
                    elif type == '2d':
                        self.residual_layer = nn.Sequential(
                            nn.Conv2d(
                                in_channels=in_channels,
                                out_channels=out_channels,
                                kernel_size=kernel_size,
                                stride=stride,
                                padding=padding
                            )
                        )
            

        in_channels = in_channels*groups
        out_channels = out_channels*groups
        if type == '1d':
            self.conv = nn.Conv1d(in_channels=in_channels, out_channels=out_channels,
                                    kernel_size=kernel_size, stride=stride, padding=padding,
                                    groups=groups)
            self.norm = nn.BatchNorm1d(out_channels)
            self.dropout = nn.Dropout(p=p)
        elif type == '2d':
            self.conv = nn.Conv2d(in_channels=in_channels, out_channels=out_channels,
                                    kernel_size=kernel_size, stride=stride, padding=padding,
                                    groups=groups)
            self.norm = nn.BatchNorm2d(out_channels)
            self.dropout = nn.Dropout2d(p=p)
        if leaky:
            self.relu = nn.LeakyReLU(negative_slope=0.2)
        else:
            self.relu = nn.ReLU()

    def forward(self, x, **kwargs):
        out = self.norm(self.dropout(self.conv(x)))
        if self.residual:
            residual = self.residual_layer(x)
            out += residual
        return self.relu(out)

class UNet1D(nn.Module):
    def __init__(self, 
                input_channels, 
                output_channels, 
                max_depth=5, 
                kernel_size=None, 
                stride=None, 
                p=0, 
                groups=1):
        super(UNet1D, self).__init__()
        self.pre_downsampling_conv = nn.ModuleList([])
        self.conv1 = nn.ModuleList([])
        self.conv2 = nn.ModuleList([])
        self.upconv = nn.Upsample(scale_factor=2, mode='nearest')
        self.max_depth = max_depth
        self.groups = groups

        
        self.pre_downsampling_conv.append(ConvNormRelu(input_channels, output_channels,
                                                    type='1d', leaky=True, downsample=False,
                                                    kernel_size=kernel_size, stride=stride, p=p, groups=groups))
        self.pre_downsampling_conv.append(ConvNormRelu(output_channels, output_channels,
                                                    type='1d', leaky=True, downsample=False,
                                                    kernel_size=kernel_size, stride=stride, p=p, groups=groups))
        
        for i in range(self.max_depth):
            self.conv1.append(ConvNormRelu(output_channels, output_channels,
                                            type='1d', leaky=True, downsample=True,
                                            kernel_size=kernel_size, stride=stride, p=p, groups=groups))

        for i in range(self.max_depth):
            self.conv2.append(ConvNormRelu(output_channels, output_channels,
                                            type='1d', leaky=True, downsample=False,
                                            kernel_size=kernel_size, stride=stride, p=p, groups=groups))

    def forward(self, x):
        
        
        input_size = x.shape[-1]
        
        
        
        assert get_log(input_size) >= self.max_depth, 'num_frames must be a power of 2 and its power must be greater than max_depth'

        x = nn.Sequential(*self.pre_downsampling_conv)(x)

        residuals = []
        residuals.append(x)
        for i, conv1 in enumerate(self.conv1):
            x = conv1(x)
            if i < self.max_depth - 1:
                residuals.append(x)

        for i, conv2 in enumerate(self.conv2):
            x = self.upconv(x) + residuals[self.max_depth - i - 1]
            x = conv2(x)

        return x

class UNet2D(nn.Module):
    def __init__(self):
        super(UNet2D, self).__init__()
        raise NotImplementedError('2D Unet并不自然')

class GraphConvNormRelu(nn.Module):
    def __init__(self,
        C_in,
        C_out,
        A,#adjacent matrix (num_parts, V, V)
        residual,
        local_bn = False,
        kernel_size=None,#时域上的卷积
        share_weights=False
    ) -> None:
        super().__init__()
        self.share_weights = share_weights

        if isinstance(A, np.ndarray):
            A = torch.from_numpy(A).to(torch.float32)
        self.register_buffer("A", A)

        if share_weights:
            print("using sharing weights graph")
            print("adjacent matrix order: self, hand, arm, body")
            print("sharing weights in the hand and arm graph")

        self.weights = nn.Parameter(torch.ones_like(A).to(torch.float32), requires_grad=True)

        self.num_joints = A.shape[1]
        self.num_parts = A.shape[0]
        self.residual = residual
        self.C_in = C_in
        self.C_out = C_out
        self.local_bn = local_bn

        self.conv_list = nn.ModuleList([])
        for i in range(self.num_parts):
            self.conv_list.append(nn.Conv2d(
                in_channels=C_in, 
                out_channels=C_out,
                kernel_size=1,
                padding=0,
                stride=1
            ))

        if self.local_bn:#每个joint的特征分别进行BN
            self.bn1 = nn.BatchNorm1d(C_out * self.num_joints)
        else:
            self.bn1 = nn.BatchNorm2d(C_out)

        self.relu = nn.ReLU()

        if kernel_size is not None:
            self.temporal_conv = ConvNormRelu(
                in_channels=C_out,
                out_channels=C_out,
                type='2d',
                kernel_size=(kernel_size, 1),
                stride=1,
                padding=((kernel_size-1)//2, 0)
            )
        else:
            self.temporal_conv = nn.Identity()

        if self.residual:
            if C_in!=C_out:
                self.shortcut = nn.Conv2d(
                    in_channels=C_in,
                    out_channels=C_out,
                    kernel_size=1,
                    stride=1,
                    padding=0
                )
            else:
                self.shortcut = nn.Identity()

    def forward(self, x):
        '''
        x: (B, D, T, V)
        '''
        B, D, T, V = x.shape

        if self.residual:
            residual = self.shortcut(x)

        if not self.share_weights:
            A = self.A * self.weights
        else:
            weights = self.weights.clone()
            #hand
            for i in range(len(left_hand_edge_list)):
                left_edge = left_hand_edge_list[i]
                right_edge = right_hand_edge_list[i]
                for j in range(len(left_edge)-1):
                    left_node_1, left_node_2 = left_edge[j], left_edge[j+1]
                    right_node_1, right_node_2 = right_edge[j], right_edge[j+1]
                    weights[1][right_node_1, right_node_2] = self.weights[1][left_node_1][left_node_2]
                    weights[1][right_node_2, right_node_1] = self.weights[1][left_node_2, left_node_1]
                    
            #arm
            for i in range(len(left_arm_edge_list)):
                left_edge = left_arm_edge_list[i]
                right_edge = right_arm_edge_list[i]
                for j in range(len(left_edge)-1):
                    left_node_1, left_node_2 = left_edge[j], left_edge[j+1]
                    right_node_1, right_node_2 = right_edge[j], right_edge[j+1]
                    weights[2][right_node_1, right_node_2] = self.weights[2][left_node_1][left_node_2]
                    weights[2][right_node_2, right_node_1] = self.weights[2][left_node_2, left_node_1]
            
            A = self.A * weights

        x = x.contiguous().view(B*self.C_in*T, self.num_joints)#(B*D*T, V)
        x_conved = 0

        #这一步图卷积的操作相当于对每个节点，将相邻节点的特征加权求和
        for i in range(self.num_parts):
            A_part = A[i] #(V, V)
            x_conved_i = torch.matmul(x, A_part)#(N, V)
            x_conved_i = x_conved_i.view(B, self.C_in, T, self.num_joints)

            x_conved_i = self.conv_list[i](x_conved_i) #(B, C_out, T, V)
            x_conved += x_conved_i #（B, C_out, T, V)

        #是否每个节点各自进行bn，注意和数据的norm方式保持一致，如果是用新的normalize的方法的话，则不需要local bn
        if self.local_bn:
            x_conved = x_conved.permute(0, 1, 3, 2).contiguous().view(B, self.C_out*self.num_joints, T)
            x_conved = self.bn1(x_conved)
            x_conved = x_conved.contiguous().view(B, self.C_out, self.num_joints, T).permute(0, 1, 3, 2)
        else:
            x_conved = self.bn1(x_conved)

        x_conved = self.relu(x_conved)

        x_conved = self.temporal_conv(x_conved)#(B, C_out, T, V)
        if self.residual:
            x_conved += residual

        return x_conved

class AudioPoseEncoder1D(nn.Module):
    '''
    将audio的feat逐步提升
    (B, C, T) -> (B, C*2, T) -> ... -> (B, C_out, T)
    '''
    def __init__(self,
        C_in, 
        C_out,
        kernel_size=None,
        stride=None,
        min_layer_nums=None
    ):
        super(AudioPoseEncoder1D, self).__init__()
        self.C_in = C_in
        self.C_out = C_out

        conv_layers = nn.ModuleList([])
        cur_C = C_in
        num_layers=0
        while cur_C < self.C_out:
            conv_layers.append(ConvNormRelu(
                in_channels=cur_C,
                out_channels=cur_C*2,
                kernel_size=kernel_size,
                stride=stride
            ))
            cur_C *= 2
            num_layers += 1
        
        if (cur_C!=C_out) or (min_layer_nums is not None and num_layers < min_layer_nums):
            while (cur_C!=C_out) or num_layers < min_layer_nums:
                conv_layers.append(ConvNormRelu(
                    in_channels=cur_C,
                    out_channels=C_out,
                    kernel_size=kernel_size,
                    stride=stride
                ))
                num_layers+=1
                cur_C = C_out
        
        self.conv_layers = nn.Sequential(*conv_layers)
    
    def forward(self, x):
        '''
        x: (B, C, T)
        '''
        x = self.conv_layers(x)
        return x

class AudioPoseEncoder2D(nn.Module):
    '''
    (B, C, T) -> (B, 1, C, T) -> ... -> (B, C_out, T)
    '''
    def __init__(self):
        raise NotImplementedError

class AudioPoseEncoderRNN(nn.Module):
    '''
    RNN形式的encoder，主要改变维度
    (B, C, T)->(B, T, C)->(B, T, C_out)->(B, C_out, T)
    '''
    def __init__(self,
        C_in,
        hidden_size,
        num_layers,
        rnn_cell = 'gru',
        bidirectional=False
    ):
        super(AudioPoseEncoderRNN, self).__init__()
        if rnn_cell == 'gru':
            self.cell = nn.GRU(input_size = C_in, hidden_size = hidden_size, num_layers = num_layers, batch_first = True, bidirectional=bidirectional)
        elif rnn_cell == 'lstm':
            self.cell = nn.LSTM(input_size = C_in, hidden_size = hidden_size, num_layers = num_layers, batch_first = True, bidirectional=bidirectional)
        else:
            raise ValueError('invalid rnn cell:%s'%(rnn_cell))

    def forward(self, x, state=None):
        
        x = x.permute(0, 2, 1) 
        x, state = self.cell(x, state) 
        x = x.permute(0, 2, 1)
        
        return x 

class AudioPoseEncoderGraph(nn.Module):
    '''
    (B, C, T)->(B, 2, V, T)->(B, 2, T, V)->(B, D, T, V)
    '''
    def __init__(self,
        layers_config,#理应是(C_in, C_out, kernel_size)的list
        A,#adjacent matrix (num_parts, V, V)
        residual,
        local_bn = False,
        share_weights = False
    ) -> None:
        super().__init__()       
        self.A = A
        self.num_joints = A.shape[1]
        self.num_parts = A.shape[0]
        self.C_in = layers_config[0][0]
        self.C_out = layers_config[-1][1]

        self.conv_layers = nn.ModuleList([
            GraphConvNormRelu(
                C_in=c_in,
                C_out=c_out,
                A = self.A,
                residual=residual,
                local_bn=local_bn,
                kernel_size=k,
                share_weights=share_weights
            ) for (c_in, c_out, k) in layers_config
        ])
        
        self.conv_layers = nn.Sequential(*self.conv_layers)

    def forward(self, x):
        '''
        x: (B, C, T), C应该是num_joints*D
        output: (B, D, T, V)
        '''
        B, C, T = x.shape
        x = x.view(B, self.num_joints, self.C_in, T) #(B, V, D, T)，D：每个joint的特征维度，注意这里V在前面
        x = x.permute(0, 2, 3, 1)#(B, D, T, V)
        assert x.shape[1] == self.C_in

        x_conved = self.conv_layers(x)

        return x_conved


class SeqEncoder2D(nn.Module):
    '''
    seq_encoder, 将一个seq数据encoding成一个vector
    (B, C, T)->(B, 1, C, T)->(B, 32, C/2, T/2)->...->(B, C_out)
    '''
    def __init__(self,
        C_in,
        T_in,
        C_out,
        min_layer_num=None
    ):
        super(SeqEncoder2D, self).__init__()
        self.C_in = C_in
        self.C_out = C_out
        self.T_in = T_in

        conv_layers = nn.ModuleList([])
        conv_layers.append(ConvNormRelu(
            in_channels=1,
            out_channels=32,
            type='2d'
        ))
        
        cur_C = 32
        cur_H = C_in
        cur_W = T_in
        num_layers = 1
        while (cur_C<C_out) or (cur_H>1) or (cur_W>1):
            ks = [3,3]
            st = [1,1]
    
            if cur_H>1:
                if cur_H>4:
                    ks[0] = 4
                    st[0] = 2
                else:
                    ks[0] = cur_H
                    st[0] = cur_H
            if cur_W>1:
                if cur_W>4:
                    ks[1] = 4
                    st[1] = 2
                else:
                    ks[1] = cur_W
                    st[1] = cur_W
            
            conv_layers.append(ConvNormRelu(
                in_channels=cur_C,
                out_channels=min(C_out, cur_C*2),
                type='2d',
                kernel_size=tuple(ks),
                stride=tuple(st)                
            ))
            cur_C = min(cur_C*2, C_out)
            if cur_H>1:
                if cur_H>4:
                    cur_H //= 2
                else: 
                    cur_H=1
            if cur_W>1:
                if cur_W>4:
                    cur_W //= 2
                else:
                    cur_W = 1
            num_layers += 1
    
        if min_layer_num is not None and (num_layers<min_layer_num):
            while num_layers < min_layer_num:
                conv_layers.append(ConvNormRelu(
                    in_channels=C_out,
                    out_channels=C_out,
                    type='2d',
                    kernel_size=1,
                    stride=1
                ))
                num_layers += 1
        
        self.conv_layers = nn.Sequential(*conv_layers)
        self.num_layers = num_layers

    def forward(self, x):
        if len(x.shape) == 3:
            x = x.unsqueeze(1)
        x = self.conv_layers(x)
        return x.squeeze()

class SeqEncoder1D(nn.Module):
    '''
    使用1D卷积的seq encoder
    (B, C, T)->(B, D)
    仅仅encoding固定长度
    '''
    def __init__(self,
        C_in,
        C_out,
        T_in,
        min_layer_nums=None
    ):
        super(SeqEncoder1D, self).__init__()
        conv_layers=nn.ModuleList([])
        cur_C = C_in
        cur_T = T_in
        self.num_layers = 0
        while (cur_C<C_out) or (cur_T>1):
            ks=3
            st=1
            if cur_T>1:
                if cur_T>4:
                    ks = 4
                    st = 2
                else:
                    ks = cur_T
                    st = cur_T
            
            conv_layers.append(ConvNormRelu(
                in_channels=cur_C,
                out_channels=min(C_out, cur_C*2),
                type='1d',
                kernel_size=ks,
                stride=st
            ))
            cur_C = min(cur_C*2, C_out)
            if cur_T>1:
                if cur_T>4:
                    cur_T = cur_T // 2
                else:
                    cur_T = 1
            self.num_layers += 1

        if min_layer_nums is not None and (self.num_layers<min_layer_nums):
            while self.num_layers < min_layer_nums:
                conv_layers.append(ConvNormRelu(
                    in_channels=C_out,
                    out_channels=C_out,
                    type='1d',
                    kernel_size=1,
                    stride=1
                ))    
                self.num_layers += 1
        self.conv_layers = nn.Sequential(*conv_layers)
    
    def forward(self, x):
        x = self.conv_layers(x)
        return x.squeeze()

class SeqEncoderRNN(nn.Module):
    '''
    基于RNN的encoder，会简单一点
    (B, C, T) -> (B, T, C) -> (B, D)
    LSTM/GRU-FC
    '''
    def __init__(self,
        hidden_size,
        in_size,
        num_rnn_layers,
        rnn_cell='gru',
        bidirectional=False
    ):
        super(SeqEncoderRNN, self).__init__()
        self.hidden_size = hidden_size
        self.in_size = in_size
        self.num_rnn_layers = num_rnn_layers
        self.bidirectional = bidirectional

        if rnn_cell == 'gru':
            self.cell = nn.GRU(input_size = self.in_size, hidden_size = self.hidden_size, num_layers = self.num_rnn_layers, batch_first = True, bidirectional=bidirectional)
        elif rnn_cell == 'lstm':
            self.cell = nn.LSTM(input_size = self.in_size, hidden_size = self.hidden_size, num_layers = self.num_rnn_layers, batch_first=True, bidirectional=bidirectional)
    
    def forward(self, x, state=None):
        
        x = x.permute(0, 2, 1)
        B,T,C = x.shape
        x,_ = self.cell(x, state)
        if self.bidirectional:
            out = torch.cat([x[:, -1, :self.hidden_size], x[:, 0, self.hidden_size:]], dim=-1)
        else:
            out = x[:, -1, :]
        assert out.shape[0] == B
        return out

class SeqEncoderGraph(nn.Module):
    def __init__(self,
        embedding_size,#整个graph的embedding size
        layer_configs,#输出的是每个节点的embedding
        residual,
        local_bn,
        A,
        T,
        share_weights=False
    ) -> None:
        super().__init__()

        self.C_in = layer_configs[0][0]
        self.C_out = embedding_size

        self.num_joints = A.shape[1]
        
        #首先是一系列的图卷积操作，调整维度
        self.graph_encoder = AudioPoseEncoderGraph(
            layers_config=layer_configs,
            A = A,
            residual = residual,
            local_bn = local_bn,
            share_weights = share_weights
        )

        cur_C = layer_configs[-1][1]
        self.spatial_pool = ConvNormRelu(
            in_channels=cur_C,
            out_channels=cur_C,
            type='2d',
            kernel_size=(1, self.num_joints),
            stride=(1, 1),
            padding=(0, 0)
        )

        temporal_pool = nn.ModuleList([])
        cur_H = T
        num_layers = 0
        self.temporal_conv_info = []
        while cur_C < self.C_out or cur_H > 1:
            self.temporal_conv_info.append(cur_C)
            #可能会导致这里的层次很多, 
            ks = [3, 1]
            st = [1, 1]
    
            if cur_H>1:
                if cur_H>4:
                    ks[0] = 4
                    st[0] = 2
                else:
                    ks[0] = cur_H
                    st[0] = cur_H

            temporal_pool.append(ConvNormRelu(
                in_channels=cur_C,
                out_channels=min(self.C_out, cur_C*2),
                type='2d',
                kernel_size=tuple(ks),
                stride=tuple(st)                
            ))
            cur_C = min(cur_C*2, self.C_out)

            if cur_H>1:
                if cur_H>4:
                    cur_H //= 2
                else: 
                    cur_H=1

            num_layers += 1
        
        self.temporal_pool = nn.Sequential(*temporal_pool)
        print("graph seq encoder info: temporal pool:", self.temporal_conv_info)
        self.num_layers = num_layers
        #need fc?
            
    def forward(self, x):
        '''
        x: (B, C, T)
        '''
        B, C, T = x.shape
        x = self.graph_encoder(x)
        x = self.spatial_pool(x)
        x = self.temporal_pool(x)
        x = x.view(B, self.C_out)

        return x


class SeqDecoder2D(nn.Module):
    '''
    '''
    def __init__(self):
        super(SeqDecoder2D, self).__init__()
        raise NotImplementedError

class SeqDecoder1D(nn.Module):
    '''
    1D卷积形式的seq decoder，将一个feature vector decode成一个sequence，和SeqEncoder系列对应
    (B, D)->(B, D, 1)->...->(B, C_out, T)
    '''
    def __init__(self,
        D_in,
        C_out,
        T_out,
        min_layer_num=None
    ):
        super(SeqDecoder1D, self).__init__()
        self.T_out = T_out
        self.min_layer_num = min_layer_num

        cur_t = 1
        
        self.pre_conv = ConvNormRelu(
            in_channels=D_in,
            out_channels=C_out,
            type='1d'
        )
        self.num_layers = 1
        self.upconv = nn.Upsample(scale_factor=2, mode='nearest')
        self.conv_layers = nn.ModuleList([])
        cur_t *= 2
        while cur_t<=T_out:
            self.conv_layers.append(ConvNormRelu(
                in_channels=C_out,
                out_channels=C_out,
                type='1d'
            ))
            cur_t *= 2
            self.num_layers += 1
        
        post_conv = nn.ModuleList([ConvNormRelu(
            in_channels=C_out,
            out_channels=C_out,
            type='1d'
        )])
        self.num_layers+=1
        if min_layer_num is not None and self.num_layers<min_layer_num:
            while self.num_layers<min_layer_num:
                post_conv.append(ConvNormRelu(
                    in_channels=C_out,
                    out_channels=C_out,
                    type='1d'
                ))
                self.num_layers += 1
        self.post_conv = nn.Sequential(*post_conv)

    def forward(self, x):
        
        x = x.unsqueeze(-1)
        x = self.pre_conv(x)
        for conv in self.conv_layers:
            x = self.upconv(x)
            x = conv(x)
        
        x = torch.nn.functional.interpolate(x, size=self.T_out, mode='nearest')
        x = self.post_conv(x)
        return x

class SeqDecoderRNN(nn.Module):
    '''
    使用RNN的seq的seq decoder
    (B, D)->(B, C_out, T)
    '''
    def __init__(self,
        hidden_size,
        C_out,
        T_out,
        num_layers,
        rnn_cell = 'gru'
    ):
        super(SeqDecoderRNN, self).__init__()
        self.num_steps = T_out
        if rnn_cell == 'gru':
            self.cell = nn.GRU(input_size = C_out, hidden_size = hidden_size, num_layers = num_layers, batch_first = True, bidirectional=False)
        elif rnn_cell == 'lstm':
            self.cell = nn.LSTM(input_size = C_out, hidden_size = hidden_size, num_layers = num_layers, batch_first = True, bidirectional=False)
        else:
            raise ValueError('invalid rnn cell:%s'%(rnn_cell))
        
        self.fc = nn.Linear(hidden_size, C_out)

    def forward(self, hidden, frame_0):
        frame_0 = frame_0.permute(0, 2, 1)
        dec_input = frame_0
        outputs = []
        for i in range(self.num_steps):
            frame_out, hidden = self.cell(dec_input, hidden)
            frame_out = self.fc(frame_out)
            dec_input = frame_out
            outputs.append(frame_out)
        output = torch.cat(outputs, dim=1)
        return output.permute(0, 2, 1)

class SeqTranslator2D(nn.Module):
    '''
    (B, C, T)->(B, 1, C, T)-> ... -> (B, 1, C_out, T_out)
    '''
    def __init__(self,
        C_in = 64,
        C_out = 108,
        T_in = 75,
        T_out = 25,
        residual = True
    ):
        super(SeqTranslator2D, self).__init__()
        print("Warning: hard coded")
        self.C_in = C_in
        self.C_out = C_out
        self.T_in = T_in
        self.T_out = T_out
        self.residual = residual

        self.conv_layers = nn.Sequential(
            ConvNormRelu(1, 32, '2d', kernel_size=5, stride=1),
            ConvNormRelu(32, 32, '2d', kernel_size=5, stride=1, residual=self.residual),
            ConvNormRelu(32, 32, '2d', kernel_size=5, stride=1, residual=self.residual),

            ConvNormRelu(32, 64, '2d', kernel_size=5, stride=(4, 3)),
            ConvNormRelu(64, 64, '2d', kernel_size=5, stride=1, residual=self.residual),
            ConvNormRelu(64, 64, '2d', kernel_size=5, stride=1, residual=self.residual),

            ConvNormRelu(64, 128, '2d', kernel_size=5, stride=(4, 1)),
            ConvNormRelu(128, 108, '2d', kernel_size=3, stride=(4, 1)),
            ConvNormRelu(108, 108, '2d', kernel_size=(1,3), stride=1, residual=self.residual),
            
            ConvNormRelu(108, 108, '2d', kernel_size=(1,3), stride=1, residual=self.residual),
            ConvNormRelu(108, 108, '2d', kernel_size=(1,3), stride=1),
        )
    
    def forward(self, x):
        assert len(x.shape)==3 and x.shape[1] == self.C_in and x.shape[2] == self.T_in
        x = x.view(x.shape[0], 1, x.shape[1], x.shape[2])
        x = self.conv_layers(x)
        x = x.squeeze(2)
        return x


class SeqTranslator1D(nn.Module):
    '''
    (B, C, T)->(B, C_out, T)
    '''
    def __init__(self,
        C_in,
        C_out,
        kernel_size=None,
        stride=None,
        min_layers_num=None
    ):
        super(SeqTranslator1D, self).__init__()
        
        conv_layers = nn.ModuleList([])
        conv_layers.append(ConvNormRelu(
            in_channels=C_in,
            out_channels=C_out,
            type='1d',
            kernel_size=kernel_size,
            stride=stride
        ))
        self.num_layers=1
        if min_layers_num is not None and self.num_layers<min_layers_num:
            while self.num_layers < min_layers_num:
                conv_layers.append(ConvNormRelu(
                    in_channels=C_out,
                    out_channels=C_out,
                    type='1d',
                    kernel_size=kernel_size,
                    stride=stride
                ))
                self.num_layers += 1
        self.conv_layers = nn.Sequential(*conv_layers)

    def forward(self, x):
        return self.conv_layers(x)

class SeqTranslatorRNN(nn.Module):
    '''
    使用RNN的seq decoder
    (B, C, T)->(B, C_out, T)
    LSTM-FC
    '''
    def __init__(self,
        C_in,
        C_out,
        hidden_size,
        num_layers,
        rnn_cell = 'gru'
    ):
        super(SeqTranslatorRNN, self).__init__()
        
        if rnn_cell == 'gru':
            self.enc_cell = nn.GRU(input_size = C_in, hidden_size = hidden_size, num_layers = num_layers, batch_first = True, bidirectional=False)
            self.dec_cell = nn.GRU(input_size = C_out, hidden_size = hidden_size, num_layers = num_layers, batch_first = True, bidirectional=False)
        elif rnn_cell == 'lstm':
            self.enc_cell = nn.LSTM(input_size = C_in, hidden_size = hidden_size, num_layers = num_layers, batch_first = True, bidirectional=False)
            self.dec_cell = nn.LSTM(input_size = C_out, hidden_size = hidden_size, num_layers = num_layers, batch_first = True, bidirectional=False)
        else:
            raise ValueError('invalid rnn cell:%s'%(rnn_cell))
        
        self.fc = nn.Linear(hidden_size, C_out)

    def forward(self, x, frame_0):
        
        num_steps = x.shape[-1]
        x = x.permute(0, 2, 1)
        frame_0 = frame_0.permute(0, 2, 1)
        _, hidden = self.enc_cell(x, None)

        outputs = []
        for i in range(num_steps):
            inputs = frame_0
            output_frame, hidden = self.dec_cell(inputs, hidden)
            output_frame = self.fc(output_frame)
            frame_0 = output_frame
            outputs.append(output_frame)
        outputs = torch.cat(outputs, dim=1)
        return outputs.permute(0, 2, 1)

class ResBlock(nn.Module):
    def __init__(self, 
        input_dim, 
        fc_dim, 
        afn, 
        nfn
    ):
        '''
        afn: activation fn
        nfn: normalization fn
        '''
        super(ResBlock, self).__init__()

        self.input_dim=input_dim
        self.fc_dim=fc_dim
        self.afn=afn
        self.nfn=nfn

        if self.afn !='relu':
            raise ValueError('Wrong')
        
        if self.nfn=='layer_norm':
            raise ValueError('wrong')

        self.layers=nn.Sequential(
            nn.Linear(self.input_dim, self.fc_dim // 2),
            nn.ReLU(),
            nn.Linear(self.fc_dim//2, self.fc_dim//2),
            nn.ReLU(),
            nn.Linear(self.fc_dim//2, self.fc_dim),
            nn.ReLU()
        )
        
        self.shortcut_layer=nn.Sequential(
            nn.Linear(self.input_dim, self.fc_dim),
            nn.ReLU(),
        )

    def forward(self, inputs):
        return self.layers(inputs)+self.shortcut_layer(inputs)

if __name__ == '__main__':
    import numpy as np
    import os
    import sys
    
    test_model = SeqTranslator2D(
    )

    input = torch.randn((64, 64, 75))
    output = test_model(input)
    print(output.shape)