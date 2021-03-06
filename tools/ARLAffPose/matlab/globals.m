function opt = globals()

opt.root = '/home/akeaveny/git/DenseFusion/';
opt.dataset_root = '/data/Akeaveny/Datasets/ARLAffPose/';

opt.classes_file = strcat(opt.root(), 'datasets/arl_affpose/dataset_config/classes.txt');

opt.keyframes = strcat(opt.root(), 'datasets/arl_affpose/dataset_config/data_lists/test_list.txt');

opt.eval_folder_gt           = strcat(opt.root(), 'tools/ARLAffPose/matlab/results/gt/');
opt.eval_folder_df_wo_refine = strcat(opt.root(), 'tools/ARLAffPose/matlab/results/df_wo_refine/');
opt.eval_folder_df_iterative = strcat(opt.root(), 'tools/ARLAffPose/matlab/results/df_iterative/');