use std::{fs::OpenOptions, process::{Command, Stdio}, sync::atomic::{AtomicI32, AtomicU32, AtomicU64, Ordering}};

use libc::{SIGUSR1, rusage, timeval, wait4};
use nix::{sys::signal::{SigHandler, Signal, kill, signal}, unistd::{Pid, alarm}};

static VALIDATOR_STATUS: AtomicI32 = AtomicI32::new(0);
static NEW_SUBMISSION_STATUS: AtomicI32 = AtomicI32::new(0);
static OLD_SUBMISSION_STATUS: AtomicI32 = AtomicI32::new(0);
static VALIDATOR_PID: AtomicI32 = AtomicI32::new(0);
static NEW_SUBMISSION_PID: AtomicI32 = AtomicI32::new(0);
static OLD_SUBMISSION_PID: AtomicI32 = AtomicI32::new(0);
static VALIDATOR_TIME: AtomicU64 = AtomicU64::new(0); //should be interpreted as a f64. see #72353
static NEW_SUBMISSION_TIME: AtomicU64 = AtomicU64::new(0);
static OLD_SUBMISSION_TIME: AtomicU64 = AtomicU64::new(0);
static TIMELIM: AtomicU32 = AtomicU32::new(0);

fn main() {
    //TODO: update atomics with better orderings
    let mut args = std::env::args();
    args.next();
    
    let timelim = args.next().unwrap().parse().unwrap();
    TIMELIM.store(timelim, Ordering::Relaxed);
    
    //create struct for running validator
    let validator_args = args.by_ref()
            .take_while(|e| e != ";")
            .collect::<Vec<_>>();
    let mut validator = Command::new(&validator_args[0]);
    validator.args(&validator_args[1..]);
    validator.stdin(Stdio::null());
    validator.stdout(Stdio::null());
    
    let validator = validator.spawn().unwrap();
    VALIDATOR_PID.store(validator.id() as i32, Ordering::Relaxed);
    
    //create struct for running new_submission
    //TODO: open files on different threads to avoid deadlocks
    let mut new_submission = {
        let mut run_cmd = args.by_ref()
            .take_while(|e| e != ";");
            
        let mut run = Command::new(run_cmd.next().unwrap());
        run.args(run_cmd);
        run.stdout(OpenOptions::new().write(true).open(&validator_args[validator_args.len() - 4]).unwrap());
        run.stdin(OpenOptions::new().read(true).open(&validator_args[validator_args.len() - 3]).unwrap());
        run.stderr(Stdio::null());
        run
    };

    //create struct for running old_submission
    let mut old_submission = {
        let mut run_cmd = args.by_ref()
            .take_while(|e| e != ";");
            
        let mut run = Command::new(run_cmd.next().unwrap());
        run.args(run_cmd);
        run.stdout(OpenOptions::new().write(true).open(&validator_args[validator_args.len() - 2]).unwrap());
        run.stdin(OpenOptions::new().read(true).open(&validator_args[validator_args.len() - 1]).unwrap());
        run.stderr(Stdio::null());
        run
    };
    
    //start the submissions
    let new_submission = new_submission.spawn().unwrap();
    NEW_SUBMISSION_PID.store(new_submission.id() as i32, Ordering::Relaxed);
    let old_submission = old_submission.spawn().unwrap();
    OLD_SUBMISSION_PID.store(old_submission.id() as i32, Ordering::Relaxed);
    
    if timelim != 0 {
        unsafe {
            signal(Signal::SIGALRM, SigHandler::Handler(handler)).unwrap();
        }
        
        alarm::set(timelim);
    }
    
    let mut remaining = 3;
    
    while remaining > 0 {
        let mut usage = blank_rusage();
        let mut status = 0;
        let done_pid = unsafe {
            wait4(-1, &mut status as *mut _, 0, &mut usage as *mut _) //emulates wait3
        };
        
        if done_pid == VALIDATOR_PID.load(Ordering::Relaxed) {
            VALIDATOR_PID.store(-1, Ordering::Relaxed);
            VALIDATOR_STATUS.store(status, Ordering::Relaxed);
            VALIDATOR_TIME.store(runtime(&usage).to_bits(), Ordering::Relaxed);
            remaining -= 1;
        } else if done_pid == NEW_SUBMISSION_PID.load(Ordering::Relaxed) {
            NEW_SUBMISSION_PID.store(-1, Ordering::Relaxed);
            NEW_SUBMISSION_STATUS.store(status, Ordering::Relaxed);
            NEW_SUBMISSION_TIME.store(runtime(&usage).to_bits(), Ordering::Relaxed);
            remaining -= 1;
            
        } else if done_pid == OLD_SUBMISSION_PID.load(Ordering::Relaxed) {
            OLD_SUBMISSION_PID.store(-1, Ordering::Relaxed);
            OLD_SUBMISSION_STATUS.store(status, Ordering::Relaxed);
            OLD_SUBMISSION_TIME.store(runtime(&usage).to_bits(), Ordering::Relaxed);
            remaining -= 1;
        }
    }
    
    println!("{} {:.6} {} {:.6} {} {:.6}",
        VALIDATOR_STATUS.load(Ordering::Relaxed),
        f64::from_bits(VALIDATOR_TIME.load(Ordering::Relaxed)), 
        NEW_SUBMISSION_STATUS.load(Ordering::Relaxed),
        f64::from_bits(NEW_SUBMISSION_TIME.load(Ordering::Relaxed)), 
        OLD_SUBMISSION_STATUS.load(Ordering::Relaxed),
        f64::from_bits(OLD_SUBMISSION_TIME.load(Ordering::Relaxed)), 
    );
}

extern "C" fn handler(_: i32) {
    let timelim = TIMELIM.load(Ordering::Relaxed) as f64;
    
    let val_pid = VALIDATOR_PID.load(Ordering::Relaxed); //This code is probaby racy, could be solved by simply disabling signals?
    let (val_time, mut val_status) = 
        if val_pid != -1 { 
            let mut val_rusage = blank_rusage();
            let mut val_status = 4;
            kill(Pid::from_raw(val_pid), Signal::SIGTERM).unwrap();
            unsafe {
                wait4(val_pid, &mut val_status as *mut _, 0, &mut val_rusage as *mut _);
            }
            (runtime(&val_rusage), 43 << 8) //assume draw if the validator had to be killed
        } else {
            (
                f64::from_bits(VALIDATOR_TIME.load(Ordering::Relaxed)), 
                VALIDATOR_STATUS.load(Ordering::Relaxed),
            )
        };
        
    let new_sub_pid = NEW_SUBMISSION_PID.load(Ordering::Relaxed);
    let (new_sub_time, mut new_sub_status) = 
        if new_sub_pid != -1 { 
            let mut new_sub_rusage = blank_rusage();
            let mut new_sub_status = 0;
            kill(Pid::from_raw(new_sub_pid), Signal::SIGKILL).unwrap();
            unsafe {
                wait4(new_sub_pid, &mut new_sub_status as *mut _, 0, &mut new_sub_rusage as *mut _);
            }
            let runtime = runtime(&new_sub_rusage);
            (runtime, SIGUSR1)
        } else {
            (
                f64::from_bits(NEW_SUBMISSION_TIME.load(Ordering::Relaxed)), 
                NEW_SUBMISSION_STATUS.load(Ordering::Relaxed),
            )
        };
    
    let old_sub_pid = OLD_SUBMISSION_PID.load(Ordering::Relaxed);
    let (old_sub_time, mut old_sub_status) = 
        if old_sub_pid != -1 { 
            let mut old_sub_rusage = blank_rusage();
            let mut old_sub_status = 0;
            kill(Pid::from_raw(old_sub_pid), Signal::SIGKILL).unwrap();
            unsafe {
                wait4(old_sub_pid, &mut old_sub_status as *mut _, 0, &mut old_sub_rusage as *mut _);
            }
            (runtime(&old_sub_rusage), SIGUSR1)
        } else {
            (
                f64::from_bits(OLD_SUBMISSION_TIME.load(Ordering::Relaxed)), 
                OLD_SUBMISSION_STATUS.load(Ordering::Relaxed),
            )
        };
        
    //if new_sub didn't get stuck and old_sub did, assume that new_sub terminated normally, to indicate that it should win
    if new_sub_time < 0.99 * timelim && old_sub_time > 0.99 * timelim {
        new_sub_status = 0;
    }
    
    //same as above
    if old_sub_time < 0.99 * timelim && new_sub_time > 0.99 * timelim {
        old_sub_status = 0;
    }
    
    //Assume draw if validator didn't terminate
    if val_status == -1 {
        val_status = 43 << 8;
    }
    
    println!("{} {:.6} {} {:.6} {} {:.6}",
        val_status, val_time,
        new_sub_status, new_sub_time,
        old_sub_status, old_sub_time,
    );
    std::process::exit(0);
}

#[inline]
fn runtime(usage: &rusage) -> f64 {
    (usage.ru_utime.tv_sec + usage.ru_stime.tv_sec) as f64 + (usage.ru_utime.tv_usec + usage.ru_stime.tv_usec) as f64 / 1_000_000.0
}

#[inline]
const fn blank_rusage() -> rusage {
    rusage {
        ru_utime: timeval {
            tv_sec: 0,
            tv_usec: 0,
        },
        ru_stime: timeval {
            tv_sec: 0,
            tv_usec: 0,
        },
        ru_maxrss: 0,
        ru_ixrss: 0,
        ru_idrss: 0,
        ru_isrss: 0,
        ru_minflt: 0,
        ru_majflt: 0,
        ru_nswap: 0,
        ru_inblock: 0,
        ru_oublock: 0,
        ru_msgsnd: 0,
        ru_msgrcv: 0,
        ru_nsignals: 0,
        ru_nvcsw: 0,
        ru_nivcsw: 0,
    }
}