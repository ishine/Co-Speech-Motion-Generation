import os
import sys
sys.path.append(os.getcwd())

from nets.layers import *
import torch
import torch.nn as nn

class Generator(nn.Module):
    def __init__(self, 
        pose_dim, 
        n_pre_poses, 
        aud_dim,
        embed_dim,
        template_dim
    ):
        super().__init__()
        self.template_dim = template_dim
        self.audio_encoder = AudioPoseEncoder1D(
            C_in=aud_dim,
            C_out=embed_dim,
            min_layer_nums=3
        )
        
        self.unet = UNet1D(
            input_channels=embed_dim,
            output_channels=embed_dim
        )
    
        
        self.pre_pose_encoder = nn.Sequential(
            nn.Linear(n_pre_poses * pose_dim, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(inplace=True),
            nn.Linear(32, 16)
        )
        
        
        self.decoder = nn.Sequential(
            ConvNormRelu(embed_dim + 16 + template_dim, embed_dim),
            ConvNormRelu(embed_dim, embed_dim),
            ConvNormRelu(embed_dim, embed_dim),
            ConvNormRelu(embed_dim, embed_dim)
        )
        self.final_out = nn.Conv1d(embed_dim, pose_dim, 1, 1)

    def forward(self, in_spec, pre_poses,  template=None, n_poses=None):
        
        if n_poses is None:
            n_poses = in_spec.shape[-1]
        if template is None and self.template_dim > 0:
            
            template = torch.randn([in_spec.shape[0], self.template_dim]).to(in_spec.device)

        self.gen_length = n_poses
        audio_feat_seq = self.audio_encoder(in_spec)  
        pre_poses = pre_poses.reshape(pre_poses.shape[0], -1)
        pre_pose_feat = self.pre_pose_encoder(pre_poses)  
        pre_pose_feat = pre_pose_feat.unsqueeze(2).repeat(1, 1, self.gen_length)
        
        if self.template_dim > 0:
            template_feat = template.unsqueeze(2).repeat(1,1, self.gen_length)
            feat = torch.cat((audio_feat_seq, pre_pose_feat, template_feat), dim=1)
        else:
            feat = torch.cat((audio_feat_seq, pre_pose_feat), dim=1)
        out = self.decoder(feat)
        out = self.final_out(out)
        return out

class Discriminator(nn.Module):
    '''
    将一个seq encoding成一个值
    
    
    '''
    def __init__(self, 
        pose_dim,
        T_in
    ):
        super(Discriminator, self).__init__()
        self.seq_enc = SeqEncoder1D(
            C_in = pose_dim,
            C_out = 1,
            T_in=T_in,
            min_layer_nums=3
        )
        
    def forward(self, x):
        
        
        out = self.seq_enc(x)
        return out.squeeze()

if __name__ == '__main__':
    test_model = Generator(
        pose_dim=108,
        n_pre_poses=4,
        aud_dim=64,
        embed_dim=256,
        template_dim=0
    )

    dummy_input = torch.randn([64, 64, 128])
    pre_poses = torch.randn(64, 108, 4)
    output = test_model(dummy_input, pre_poses)
    print(output.shape)
