""" A script to hold some utility functions for model logging. """
import numpy as np
import time
import wandb
import sys
import torch


def print_status(mode, args, items):
    """
    Handles all status printing updates for the model. Allows complex string formatting per method while shrinking
    the number of lines of code per each training subroutine. mode is one of 'train_epoch', 'eval_epoch',
    'train_train', 'train_val', or 'train_test'.

    'train_epoch' refers to print statements within a training epoch,
    'eval_epoch' refers to print statemetns within an evaluation epoch,
    'train_train' refers to the end of a training epoch,
    'train_val' refers to the end of a validation epoch, and
    'train_test' refers to the end of a test epoch.
    """
    if mode == "train_epoch":
        pbar, metrics, src_seq = items
        cur_lr = metrics["history-lr"][-1]
        training_losses = metrics["train"]["batch-history"]
        train_drmsd_loss = metrics["train"]["batch-drmsd"]
        train_mse_loss = metrics["train"]["batch-mse"]
        train_comb_loss = metrics["train"]["batch-combined"]
        batch_time = metrics["train"]["batch-time"]
        if args.combined_loss:
            loss = train_comb_loss
        else:
            loss = metrics["train"]["batch-ln-drmsd"]
        lr_string = f", LR = {cur_lr:.7f}" if args.lr_scheduling else ""
        speed = metrics["train"]["speed"]

        if not args.cluster and len(training_losses) > 32:
            pbar.set_description('\r  - (Train) drmsd = {0:.6f}, ln-drmsd = {lnd:0.6f}, rmse = {3:.6f}, 32avg = {1:.6f}'
                                 ', comb = {4:.6f}{2}, res/sec = {speed}'.format(float(train_drmsd_loss),
                                                              np.mean(training_losses[-32:]),
                                                              lr_string, np.sqrt(float(train_mse_loss)),
                                                              float(train_comb_loss),
                                                              lnd=metrics["train"]["batch-ln-drmsd"],
                                                              speed=speed))
        elif not args.cluster:
            pbar.set_description('\r  - (Train) drmsd = {0:.6f}, ln-drmsd = {lnd:0.6f}, rmse = {2:.6f}, comb = '
                                 '{3:.6f}{1}, res/sec = {speed}'.format(
                float(train_drmsd_loss), lr_string, np.sqrt(float(train_mse_loss)), float(train_comb_loss),
                lnd=metrics["train"]["batch-ln-drmsd"], speed=speed))
        if args.cluster and len(training_losses) > 32:
            print('Loss = {0:.6f}, 32avg = {1:.6f}{2}, speed = {speed}'.format(
                float(loss), np.mean(training_losses[-32:]), lr_string, speed=speed))
        elif args.cluster and len(training_losses) <= 32:
            print('Loss = {0:.6f}, 32avg = {1:.6f}{2}, speed = {speed}'.format(
                float(loss), np.mean(training_losses), lr_string, speed=speed))

    elif mode == "eval_epoch":
        pbar, d_loss, mode, m_loss, c_loss = items
        if not args.cluster:
            pbar.set_description('\r  - (Eval-{1}) drmsd = {0:.6f}, rmse = {2:.6f}, comb = {3:.6f}'.format(
                float(d_loss), mode, np.sqrt(float(m_loss)), float(c_loss)))

    elif mode == "train_train":
        start, metrics = items
        cur_lr = metrics["history-lr"][-1]
        train_drmsd_loss = metrics["train"]["batch-drmsd"]
        train_mse_loss = metrics["train"]["batch-mse"]
        train_rmsd_loss_str = "{:6.3f}".format(metrics["train"]["batch-rmsd"]) if metrics["train"]["batch-rmsd"] else "nan"
        train_comb_loss = metrics["train"]["batch-combined"]
        print('\r  - (Train)   drmsd: {d: 6.3f}, rmse: {m: 6.3f}, rmsd: {rmsd}, comb: {comb: 6.3f}, '
              'elapse: {elapse:3.3f} min, lr: {lr: {lr_precision}}, res/sec = {speed}'.format(d=train_drmsd_loss,
                                                                            m=np.sqrt(train_mse_loss),
                                                                            elapse=(time.time() - start) / 60,
                                                                            lr=cur_lr, rmsd=train_rmsd_loss_str,
                                                                            comb=train_comb_loss,
                                                                            lr_precision="5.2e"
                                                                            if (cur_lr < .001 and cur_lr != 0) else
                                                                            "5.3f",
                                                                            speed = round(np.mean(metrics["train"]["speed-history"]), 2)))
    elif mode == "train_val":
        start, metrics = items
        val_drmsd_loss = metrics["valid"]["epoch-drmsd"]
        val_mse_loss = metrics["valid"]["epoch-mse"]
        val_rmsd_loss = metrics["valid"]["epoch-rmsd"]
        val_comb_loss = metrics["valid"]["epoch-combined"]
        print('\r  - (Validation) drmsd: {d: 6.3f}, rmse: {m: 6.3f}, rmsd: {rmsd: 6.3f}, comb: {comb: 6.3f}, '
              'elapse: {elapse:3.3f} min'.format(d=val_drmsd_loss, m=np.sqrt(val_mse_loss),
                                                 elapse=(time.time() - start) / 60, rmsd=val_rmsd_loss,
                                                 comb=val_comb_loss))
    elif mode == "train_test":
        start, metrics = items
        test_drmsd_loss = metrics["test"]["epoch-drmsd"]
        test_mse_loss = metrics["test"]["epoch-mse"]
        test_rmsd_loss = metrics["test"]["epoch-rmsd"]
        test_comb_loss = metrics["test"]["epoch-combined"]
        print('\r  - (Test) drmsd: {d: 6.3f}, rmse: {m: 6.3f}, rmsd: {rmsd: 6.3f}, comb: {comb: 6.3f}, '
              'elapse: {elapse:3.3f} min'.format(d=test_drmsd_loss, m=np.sqrt(test_mse_loss),
                                                 elapse=(time.time() - start) / 60, comb=test_comb_loss,
                                                 rmsd=test_rmsd_loss))
        wandb.run.summary["test_drmsd_loss"] = metrics["test"]["epoch-drmsd"]
        wandb.run.summary["test_mse_loss"] = metrics["test"]["epoch-mse"]
        wandb.run.summary["test_rmsd_loss"] = metrics["test"]["epoch-rmsd"]
        wandb.run.summary["test_comb_loss"] = metrics["test"]["epoch-combined"]


def update_loss_trackers(args, epoch_i, metrics):
    """ Updates the current loss to compare according to an early stopping policy."""
    if args.train_only:
        mode = "train"
    else:
        mode = "valid"
    if args.combined_loss:
        loss_str = "combined"
    else:
        loss_str = "drmsd"

    loss_to_compare = metrics[mode][f"epoch-{loss_str}"]
    losses_to_compare = metrics[mode][f"epoch-history-{loss_str}"]

    if loss_to_compare < metrics["best_valid_loss_so_far"]:
        metrics["best_valid_loss_so_far"] = loss_to_compare
        metrics["epoch_last_improved"] = epoch_i
    elif args.early_stopping and epoch_i - metrics["epoch_last_improved"] > args.early_stopping:
        # Model hasn't improved in X epochs
        print("No improvement for {} epochs. Stopping model training early.".format(args.early_stopping))
        raise EarlyStoppingCondition

    metrics["loss_to_compare"] = loss_to_compare
    metrics["losses_to_compare"] = losses_to_compare

    return metrics


def log_batch(log_writer, metrics, start_time,  mode="valid", end_of_epoch=False, t=None):
    """ Logs training info to an already instantiated CSV-writer log. """
    if not t:
        t = time.time()
    m = metrics[mode]
    if end_of_epoch:
        be = "epoch"
    else:
        be = "batch"
    log_writer.writerow([m[f"{be}-drmsd"], m[f"{be}-ln-drmsd"], np.sqrt(m[f"{be}-mse"]),
                         m[f"{be}-rmsd"], m[f"{be}-combined"], metrics["history-lr"][-1],
                         mode, "epoch", round(t - start_time, 4), m["speed"]])


def do_train_batch_logging(metrics, d_loss, ln_d_loss, m_loss, c_loss, src_seq, loss, optimizer, args, log_writer, pbar,
                           start_time, pred_coords, tgt_coords, step):
    """
    Performs all necessary logging at the end of a batch in the training epoch.
    Updates custom metrics dictionary and wandb logs. Prints status of training.
    Also checks for NaN losses.
    """
    do_log_str = not step or args.log_structure_step % step == 0

    metrics = update_metrics(metrics, "train", d_loss, ln_d_loss, m_loss, c_loss, src_seq,
                             tracking_loss=loss, batch_level=True)
    if not step or args.log_wandb_step % step == 0:
        wandb.log({"Train RMSE": np.sqrt(m_loss.item()),
                   "Train DRMSD": d_loss,
                   "Train ln-DRMSD": ln_d_loss,
                   "Train Combined Loss": c_loss,
                   "Train Speed": metrics["train"]["speed"]}, commit=(not args.lr_scheduling and not do_log_str))
    if args.lr_scheduling:
        metrics["history-lr"].append(optimizer.cur_lr)
        if not step or args.log_wandb_step % step == 0:
            wandb.log({"Learning Rate": optimizer.cur_lr}, commit=not do_log_str)
    log_batch(log_writer, metrics, start_time, mode="train", end_of_epoch=False)
    print_status("train_epoch", args, (pbar, metrics, src_seq))
    # Check for NaNs
    if np.isnan(loss.item()):
        print("A nan loss has occurred. Exiting training.")
        sys.exit(1)
    if do_log_str:
        log_structure(pred_coords, tgt_coords)


def log_structure(pred_coords, gold_item):
    gold_item_non_nan = torch.isnan(gold_item).eq(0)
    bb_mask = np.asarray([[1, 1, 1] + [0] * 10] * (pred_coords.shape[0] // 13), dtype=np.bool)
    wandb.log({"backbone_cloud": wandb.Object3D(
        pred_coords[bb_mask.flatten() & gold_item_non_nan.cpu().detach().numpy().all(axis=1)].detach().numpy())},
        commit=False)
    wandb.log({"structure_cloud": wandb.Object3D(pred_coords[gold_item_non_nan].reshape(-1,3).detach().numpy())})



def do_eval_epoch_logging(metrics, d_loss, ln_d_loss, m_loss, c_loss, r_loss, src_seq, args, pbar, mode):
    """
    Performs all necessary logging at the end of an evaluation epoch.
    Updates custom metrics dictionary and wandb logs. Prints status of training.
    """
    metrics = update_metrics(metrics, mode, d_loss, ln_d_loss, m_loss, c_loss, src_seq, r_loss, batch_level=False)
    wandb.log({f"{mode.title()} RMSE": np.sqrt(m_loss.item()),
               f"{mode.title()} RMSD": r_loss,
               f"{mode.title()} DRMSD": d_loss,
               f"{mode.title()} ln-DRMSD": ln_d_loss,
               f"{mode.title()} Combined Loss": c_loss,
               f"{mode.title()} Speed": metrics[mode]["speed"]})
    print_status("eval_epoch", args, (pbar, d_loss, mode, m_loss, c_loss))


def init_metrics(args):
    """ Returns an empty metric dictionary for recording model performance. """
    metrics = {"train": {"epoch-history-drmsd": [],
                         "epoch-history-combined": []},
               "valid": {"epoch-history-drmsd": [],
                         "epoch-history-combined": []},
               "test":  {"epoch-history-drmsd": [],
                         "epoch-history-combined": []},
               "history-lr": [],
               "epoch_last_improved": -1,
               "best_valid_loss_so_far": np.inf,
               }
    if not args.lr_scheduling:
        metrics["history-lr"] = [0]
    return metrics


def update_metrics(metrics, mode, drmsd, ln_drmsd, mse, combined, src_seq, rmsd=None, tracking_loss=None, batch_level=True):
    """
    Records relevant metrics in the metrics data structure while training.
    If batch_level is true, this means the loss for the current batch is
    recorded in addition to the running epoch loss.
    """
    # Update loss values
    if batch_level:
        metrics[mode]["batch-drmsd"] = drmsd.item()
        metrics[mode]["batch-ln-drmsd"] = ln_drmsd.item()
        metrics[mode]["batch-mse"] = mse.item()
        metrics[mode]["batch-combined"] = combined.item()
        if rmsd: metrics[mode]["batch-rmsd"] = rmsd.item()
    metrics[mode]["epoch-drmsd"] += drmsd.item()
    metrics[mode]["epoch-ln-drmsd"] += ln_drmsd.item()
    metrics[mode]["epoch-mse"] += mse.item()
    metrics[mode]["epoch-combined"] += combined.item()
    if rmsd: metrics[mode]["epoch-rmsd"] += rmsd.item()

    # Compute and update speed
    num_res = (src_seq != 0).any(dim=-1).sum().item()
    metrics[mode]["speed"] = round(num_res / (time.time() - metrics[mode]["batch-time"]), 2)
    metrics[mode]["batch-time"] = time.time()
    metrics[mode]["speed-history"].append(metrics[mode]["speed"])

    if tracking_loss:
        metrics[mode]["batch-history"].append(float(tracking_loss))
    return metrics


def reset_metrics_for_epoch(metrics, mode):
    """ Resets the running and batch-specific metrics for a new epoch. """
    metrics[mode]["epoch-drmsd"] = metrics[mode]["batch-drmsd"] = 0
    metrics[mode]["epoch-ln-drmsd"] = metrics[mode]["batch-ln-drmsd"] = 0
    metrics[mode]["epoch-mse"] = metrics[mode]["batch-mse"] = 0
    metrics[mode]["epoch-combined"] = metrics[mode]["batch-combined"] = 0
    if mode == "train":
        metrics[mode]["epoch-rmsd"] = metrics[mode]["batch-rmsd"] = None
    else:
        metrics[mode]["epoch-rmsd"] = metrics[mode]["batch-rmsd"] = 0
    metrics[mode]["batch-history"] = []
    metrics[mode]["batch-time"] = time.time()
    metrics[mode]["speed-history"] = []
    return metrics


def update_metrics_end_of_epoch(metrics, mode, n_batches):
    """ Averages the running metrics over an epoch """
    metrics[mode]["epoch-drmsd"] /= n_batches
    metrics[mode]["epoch-ln-drmsd"] /= n_batches
    metrics[mode]["epoch-mse"] /= n_batches
    metrics[mode]["epoch-combined"] /= n_batches
    # We don't bother to compute rmsd when training, but is included in the metrics for completeness
    if mode == "train":
        metrics[mode]["epoch-rmsd"] = None
    else:
        metrics[mode]["epoch-rmsd"] /= n_batches
    metrics[mode]["epoch-history-combined"].append(metrics[mode]["epoch-combined"])
    metrics[mode]["epoch-history-drmsd"].append(metrics[mode]["epoch-drmsd"])
    return metrics


def prepare_log_header(args):
    """ Returns the column ordering for the logfile. """
    if args.combined_loss:
        return 'drmsd,ln_drmsd,rmse,rmsd,combined,lr,mode,granularity,time,speed\n'
    else:
        return 'drmsd,ln_drmsd,rmse,rmsd,lr,mode,granularity,time,speed\n'


class EarlyStoppingCondition(Exception):
    """An exception to raise when Early Stopping conditions are met."""
    def __init__(self, *args):
        super().__init__(*args)
