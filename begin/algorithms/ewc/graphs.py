import torch
import torch.nn.functional as F
from begin.trainers.graphs import GCTrainer

class GCTaskILEWCTrainer(GCTrainer):
    def __init__(self, model, scenario, optimizer_fn, loss_fn, device, **kwargs):
        """
            EWC needs `lamb`, the additional hyperparamter for the regularization term used in :func:`afterInference`.
        """
        super().__init__(model.to(device), scenario, optimizer_fn, loss_fn, device, **kwargs)
        self.lamb = kwargs['lamb'] if 'lamb' in kwargs else 10000.
        
    def inference(self, model, _curr_batch, training_states):
        """
            The event function to execute inference step.
        
            For task-IL, we need to additionally consider task information for the inference step.
        
            Args:
                model (torch.nn.Module): the current trained model.
                curr_batch (object): the data (or minibatch) for the current iteration.
                curr_training_states (dict): the dictionary containing the current training states.
                
            Returns:
                A dictionary containing the inference results, such as prediction result and loss.
        """
        graphs, labels, masks = _curr_batch
        preds = model(graphs.to(self.device),
                      graphs.ndata['feat'].to(self.device) if 'feat' in graphs.ndata else None,
                      edge_attr = graphs.edata['feat'].to(self.device) if 'feat' in graphs.edata else None,
                      edge_weight = graphs.edata['weight'].to(self.device) if 'weight' in graphs.edata else None,
                      task_masks = masks)
        loss = self.loss_fn(preds, labels.to(self.device))
        return {'preds': preds, 'loss': loss}

    def afterInference(self, results, model, optimizer, _curr_batch, training_states):
        """
            The event function to execute some processes right after the inference step (for training).
            We recommend performing backpropagation in this event function.
            
            EWC performs regularization process in this function.
            
            Args:
                results (dict): the returned dictionary from the event function `inference`.
                model (torch.nn.Module): the current trained model.
                optimizer (torch.optim.Optimizer): the current optimizer function.
                curr_batch (object): the data (or minibatch) for the current iteration.
                curr_training_states (dict): the dictionary containing the current training states.
                
            Returns:
                A dictionary containing the information from the `results`.
        """
        loss_reg = 0.
        for _param, _fisher in zip(training_states['params'], training_states['fishers']):
            for name, p in model.named_parameters():
                l = self.lamb * _fisher[name]
                l = l * ((p - _param[name]) ** 2)
                loss_reg = loss_reg + l.sum()
        total_loss = results['loss'] + loss_reg
        total_loss.backward()
        optimizer.step()
        return {'_num_items': results['preds'].shape[0],
                'loss': total_loss.item(),
                'acc': self.eval_fn(self.predictionFormat(results), _curr_batch[1].to(self.device))}
    
    def initTrainingStates(self, scenario, model, optimizer):
        return {'fishers': [], 'params': []}
    
    def processAfterTraining(self, task_id, curr_dataset, curr_model, curr_optimizer, curr_training_states):
        """
            The event function to execute some processes after training the current task.
            
            EWC computes fisher information matrix and stores the learned weights to compute the penalty term in :func:`afterInference`
                
            Args:
                task_id (int): the index of the current task.
                curr_dataset (object): The dataset for the current task.
                curr_model (torch.nn.Module): the current trained model.
                curr_optimizer (torch.optim.Optimizer): the current optimizer function.
                curr_training_states (dict): the dictionary containing the current training states.
        """
        super().processAfterTraining(task_id, curr_dataset, curr_model, curr_optimizer, curr_training_states)
        params = {name: torch.zeros_like(p) for name, p in curr_model.named_parameters()}
        fishers = {name: torch.zeros_like(p) for name, p in curr_model.named_parameters()}
        train_loader = self.prepareLoader(curr_dataset, curr_training_states)[0]
        
        total_num_items = 0
        for i, _curr_batch in enumerate(iter(train_loader)):
            curr_model.zero_grad()
            curr_results = self.inference(curr_model, _curr_batch, curr_training_states)
            curr_results['loss'].backward()
            curr_num_items =_curr_batch[1].shape[0]
            total_num_items += curr_num_items
            for name, p in curr_model.named_parameters():
                params[name] = p.data.clone().detach()
                if p.grad is not None: fishers[name] += (p.grad.data.clone().detach() ** 2) * curr_num_items
                    
        for name, p in curr_model.named_parameters():
            fishers[name] /= total_num_items
                
        curr_training_states['fishers'].append(fishers)
        curr_training_states['params'].append(params)
        
class GCClassILEWCTrainer(GCTrainer):
    def __init__(self, model, scenario, optimizer_fn, loss_fn, device, **kwargs):
        """
            EWC needs `lamb`, the additional hyperparamter for the regularization term used in :func:`afterInference`.
        """
        super().__init__(model.to(device), scenario, optimizer_fn, loss_fn, device, **kwargs)
        self.lamb = kwargs['lamb'] if 'lamb' in kwargs else 10000.
        
    def afterInference(self, results, model, optimizer, _curr_batch, training_states):
        """
            The event function to execute some processes right after the inference step (for training).
            We recommend performing backpropagation in this event function.
            
            EWC performs regularization process in this function.
            
            Args:
                results (dict): the returned dictionary from the event function `inference`.
                model (torch.nn.Module): the current trained model.
                optimizer (torch.optim.Optimizer): the current optimizer function.
                curr_batch (object): the data (or minibatch) for the current iteration.
                curr_training_states (dict): the dictionary containing the current training states.
                
            Returns:
                A dictionary containing the information from the `results`.
        """
        loss_reg = 0.
        for _param, _fisher in zip(training_states['params'], training_states['fishers']):
            for name, p in model.named_parameters():
                l = self.lamb * _fisher[name]
                l = l * ((p - _param[name]) ** 2)
                loss_reg = loss_reg + l.sum()
        total_loss = results['loss'] + loss_reg
        total_loss.backward()
        optimizer.step()
        return {'_num_items': results['preds'].shape[0],
                'loss': total_loss.item(),
                'acc': self.eval_fn(self.predictionFormat(results), _curr_batch[1].to(self.device))}
    
    def initTrainingStates(self, scenario, model, optimizer):
        return {'fishers': [], 'params': []}
    
    def processAfterTraining(self, task_id, curr_dataset, curr_model, curr_optimizer, curr_training_states):
        """
            The event function to execute some processes after training the current task.
            
            EWC computes fisher information matrix and stores the learned weights to compute the penalty term in :func:`afterInference`
                
            Args:
                task_id (int): the index of the current task.
                curr_dataset (object): The dataset for the current task.
                curr_model (torch.nn.Module): the current trained model.
                curr_optimizer (torch.optim.Optimizer): the current optimizer function.
                curr_training_states (dict): the dictionary containing the current training states.
        """
        super().processAfterTraining(task_id, curr_dataset, curr_model, curr_optimizer, curr_training_states)
        params = {name: torch.zeros_like(p) for name, p in curr_model.named_parameters()}
        fishers = {name: torch.zeros_like(p) for name, p in curr_model.named_parameters()}
        train_loader = self.prepareLoader(curr_dataset, curr_training_states)[0]
        
        total_num_items = 0
        for i, _curr_batch in enumerate(iter(train_loader)):
            curr_model.zero_grad()
            curr_results = self.inference(curr_model, _curr_batch, curr_training_states)
            curr_results['loss'].backward()
            curr_num_items =_curr_batch[1].shape[0]
            total_num_items += curr_num_items
            for name, p in curr_model.named_parameters():
                params[name] = p.data.clone().detach()
                if p.grad is not None: fishers[name] += (p.grad.data.clone().detach() ** 2) * curr_num_items
                    
        for name, p in curr_model.named_parameters():
            fishers[name] /= total_num_items
                
        curr_training_states['fishers'].append(fishers)
        curr_training_states['params'].append(params)

class GCDomainILEWCTrainer(GCClassILEWCTrainer):
    """
        This trainer has the same behavior as `GCClassILEWCTrainer`.
    """
    pass
        
class GCTimeILEWCTrainer(GCClassILEWCTrainer):
    """
        This trainer has the same behavior as `GCClassILEWCTrainer`.
    """
    pass