"""
This is a script to test the basic training pipeline (vertex & face model)
by fitting the model to the meshes in the  `image_meshes/` directory.

The original implementation was done for image-vertex and face models. It has
been slightly modified.
"""
import torch
import torch.nn as nn
from torch.distributions.categorical import Categorical

from tqdm import tqdm

from polygen.modules.data_modules import PolygenDataModule, CollateMethod
from polygen.modules.vertex_model import ImageToVertexModel, VertexModel
from polygen.modules.face_model import FaceModel
import polygen.utils.data_utils as data_utils


def load_dataloaders():
    # img_data_module = PolygenDataModule(data_dir = "image_meshes/",
    #                                     collate_method = CollateMethod.IMAGES,
    #                                     batch_size = 4,
    #                                     training_split = 1.0,
    #                                     val_split = 0.0,
    #                                     use_image_dataset = True,
    #                                     img_extension = "png",
    #                                     apply_random_shift_vertices = False,
    # )

    # img_dataset = img_data_module.shapenet_dataset

    vertex_data_module = PolygenDataModule(data_dir = "image_meshes/",
                                        collate_method = CollateMethod.VERTICES,
                                        batch_size = 2,
                                        training_split = 1.0,
                                        val_split = 0.0,
                                        use_image_dataset = False,
                                        img_extension = "png",
                                        apply_random_shift_vertices = False,
    )
    vertex_dataset = vertex_data_module.shapenet_dataset


    face_data_module = PolygenDataModule(data_dir = "image_meshes/",
                                        collate_method = CollateMethod.FACES,
                                        batch_size = 2,
                                        training_split = 1.0,
                                        val_split = 0.0,
                                        use_image_dataset = False, # changed this
                                        img_extension = "png",
                                        apply_random_shift_faces = False,
                                        shuffle_vertices = False,
    )

    # img_data_module.setup()
    vertex_data_module.setup()
    face_data_module.setup()

    # img_dataloader = img_data_module.train_dataloader()
    vertex_dataloader = vertex_data_module.train_dataloader()
    face_dataloader = face_data_module.train_dataloader()

    return vertex_data_module, vertex_dataset, vertex_dataloader, face_dataloader

def plot_input_meshes(img_dataset):
    mesh_list = []
    for i in range(len(img_dataset)):
        mesh_dict = img_dataset[i]
        curr_verts, curr_faces = mesh_dict['vertices'], mesh_dict['faces']
        curr_verts = data_utils.dequantize_verts(curr_verts).numpy()
        curr_faces = data_utils.unflatten_faces(curr_faces.numpy())
        mesh_list.append({'vertices': curr_verts, 'faces': curr_faces})

    data_utils.plot_meshes(mesh_list, ax_lims = 0.4)

def load_models():
    img_decoder_config = {
        "hidden_size": 256,
        "fc_size": 1024,
        "num_layers": 5,
        'dropout_rate': 0.
    }

    face_transformer_config = {
        'hidden_size': 256,
        'fc_size': 1024,
        'num_layers': 3,
        'dropout_rate': 0.
    }

    # img_model = ImageToVertexModel(
    #     decoder_config = img_decoder_config,
    #     max_num_input_verts = 800,
    #     quantization_bits = 8,
    #     learning_rate = 5e-4,
    #     gamma = 1.
    # )

    vertex_model = VertexModel(
        decoder_config = img_decoder_config,
        max_num_input_verts = 800,
        quantization_bits = 8,
        learning_rate = 5e-4,
        gamma = 1.
    )

    face_model = FaceModel(encoder_config = face_transformer_config,
                           decoder_config = face_transformer_config,
                           class_conditional = False,
                           max_seq_length = 500,
                           quantization_bits = 8,
                           decoder_cross_attention = False,
                           use_discrete_vertex_embeddings = True,
                           learning_rate = 5e-4,
                           gamma = 1.0,
                        #    gammcollate_vertex_model_batcha = 1.,
                          )

    return vertex_model, face_model

def sample_and_plot(vertex_model, vertex_batch, face_model):
    with torch.no_grad():
        vertex_samples = vertex_model.sample(context = vertex_batch, num_samples = vertex_batch["class_label"].shape[0], max_sample_length = 200,
                                        top_p = 0.95, recenter_verts = False, only_return_complete=False)
        max_vertices = torch.max(vertex_samples["num_vertices"]).item()
        vertex_samples["vertices"] = vertex_samples["vertices"][:, :max_vertices]
        vertex_samples["vertices_mask"] = vertex_samples["vertices_mask"][:, :max_vertices]
        face_samples = face_model.sample(context = vertex_samples, max_sample_length=500, top_p = 0.95, only_return_complete=False)
    mesh_list = []
    for i in range(vertex_samples["vertices"].shape[0]):
        num_vertices = vertex_samples["num_vertices"][i]
        vertices = vertex_samples["vertices"][i][:num_vertices].numpy()
        num_face_indices = face_samples['num_face_indices'][i]
        faces = data_utils.unflatten_faces(face_samples["faces"][i][:num_face_indices].numpy())
        mesh_list.append({'vertices': vertices, 'faces': faces})
    data_utils.plot_meshes(mesh_list, ax_lims = 0.5)

def sample_and_plot_vertices(vertex_model, vertex_batch):
    with torch.no_grad():
        vertex_samples = vertex_model.sample(context = vertex_batch, num_samples = vertex_batch["class_label"].shape[0],
                                            max_sample_length = 200, top_p = 0.95, recenter_verts = False, only_return_complete = False)

    mesh_list = []
    for i in range(vertex_samples["vertices"].shape[0]):
        num_vertices = vertex_samples["num_vertices"][i]
        vertices = vertex_samples["vertices"][i][:num_vertices].numpy()
        mesh_list.append({'vertices': vertices})

    data_utils.plot_meshes(mesh_list, ax_lims = 0.5)

def sample_and_plot_faces(face_model, face_batch):
    with torch.no_grad():
        face_samples = face_model.sample(context = face_batch, max_sample_length = 500, top_p = 0.95, only_return_complete = False)
    mesh_list = []
    for i in range(face_samples["faces"].shape[0]):
        curr_faces = face_samples["faces"][i]
        num_face_indices = face_samples['num_face_indices'][i]
        curr_faces = data_utils.unflatten_faces(curr_faces[:num_face_indices].numpy())
        vertices = face_batch["vertices"][i].numpy()
        mesh_list.append({'vertices': vertices, 'faces': curr_faces})

    data_utils.plot_meshes(mesh_list, ax_lims = 0.5)

def train_models(vertex_dataloader, face_dataloader):
    vertex_model, face_model = load_models()
    epochs = 500
    vertex_model_optimizer = vertex_model.configure_optimizers()["optimizer"]
    face_model_optimizer = face_model.configure_optimizers()["optimizer"]
    for i in tqdm(range(epochs)):
        for j, (vertex_batch, face_batch) in enumerate(zip(vertex_dataloader, face_dataloader)):
            vertex_model_optimizer.zero_grad()
            face_model_optimizer.zero_grad()

            vertex_logits = vertex_model(vertex_batch) # the model receives the *whole* sequence + 1 STOP token
            # TODO fix keyword arguments for the face model, ignoring it for now
            # face_logits = face_model(face_batch)
            face_logits=None

            vertex_pred_dist = Categorical(logits = vertex_logits) # logits have shape [B, max_vertex_in_batch + 1, vocab_size]
            face_pred_dist = Categorical(logits = face_logits)

            vertex_loss = -torch.sum(vertex_pred_dist.log_prob(vertex_batch["vertices_flat"]) * vertex_batch["vertices_flat_mask"])
            face_loss = -torch.sum(face_pred_dist.log_prob(face_batch["faces"]) * face_batch["faces_mask"])

            vertex_loss.backward()
            face_loss.backward()

            vertex_model_optimizer.step()
            face_model_optimizer.step()

        if ((i + 1) % 50 == 0):
            print(f"Epoch {i + 1}: Vertex loss = {vertex_loss.item()}, Face loss = {face_loss.item()}")

    return vertex_model, face_model

# Construct custom batch with 1 image for each object
def sample_from_dataset(img_data_module, img_dataset, vertex_model, face_model):
    batch = [img_dataset[0], img_dataset[4], img_dataset[8], img_dataset[12]]
    img_batch = img_data_module.collate_img_model_batch(batch)
    sample_and_plot(vertex_model, img_batch, face_model)


vertex_data_module, vertex_dataset, vertex_dataloader, face_dataloader = load_dataloaders()
train_models(vertex_dataloader, face_dataloader)