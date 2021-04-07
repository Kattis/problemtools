use std::{process::Stdio, time::{Duration, Instant}};

use tokio::{fs::OpenOptions, join, process::Command, time::timeout};
use libc::{SIGUSR1};

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(),()> {
    let mut args = std::env::args();
    args.next();
    
    let timelim = args.next().unwrap().parse().unwrap();
    
    //create struct for running validator
    //TODO: deal with stderr
    let validator_args = args.by_ref()
            .take_while(|e| e != ";")
            .collect::<Vec<_>>();
    let mut validator = Command::new(&validator_args[0]);
    validator.args(&validator_args[1..]);
    validator.stdin(Stdio::null());
    validator.stdout(Stdio::null());
    
    let validator_start_time = Instant::now();
    let mut validator = validator.spawn().unwrap();
    
    //create struct for running new_submission
    let new_submission = async {
        let mut run_cmd = args.by_ref()
            .take_while(|e| e != ";");
            
        let mut run = Command::new(run_cmd.next().unwrap());
        run.args(run_cmd);
        run.stdout(OpenOptions::new().write(true).open(&validator_args[validator_args.len() - 4]).await.unwrap().into_std().await);
        run.stdin(OpenOptions::new().read(true).open(&validator_args[validator_args.len() - 3]).await.unwrap().into_std().await);
        run
    };

    let new_submission_start_time = Instant::now();
    let mut new_submission = new_submission.await.spawn().unwrap();
    
    //create struct for running old_submission
    let old_submission = async {
        let mut run_cmd = args.by_ref()
            .take_while(|e| e != ";");
            
        let mut run = Command::new(run_cmd.next().unwrap());
        run.args(run_cmd);
        run.stdout(OpenOptions::new().write(true).open(&validator_args[validator_args.len() - 2]).await.unwrap().into_std().await);
        run.stdin(OpenOptions::new().read(true).open(&validator_args[validator_args.len() - 1]).await.unwrap().into_std().await);
        run
    };
    
    //start the submissions
    let old_submission_start_time = Instant::now();
    let mut old_submission = old_submission.await.spawn().unwrap();
    
    let mut validator_status = 0;
    let mut validator_time: f64 = 0.0;
    let mut new_submission_status = 0;
    let mut new_submission_time: f64 = 0.0;
    let mut old_submission_status = 0;
    let mut old_submission_time: f64 = 0.0;
    
    let _ = timeout(Duration::from_secs(timelim), async {
        join!(
            async {
                let code = validator.wait().await.unwrap().code().unwrap();
                validator_status = code << 8;
                validator_time = validator_start_time.elapsed().as_secs_f64();
            },
            async {
                let code = new_submission.wait().await.unwrap().code().unwrap();
                new_submission_status = code << 8;
                new_submission_time = new_submission_start_time.elapsed().as_secs_f64();
            },
            async {
                let code = old_submission.wait().await.unwrap().code().unwrap();
                old_submission_status = code << 8;
                old_submission_time = old_submission_start_time.elapsed().as_secs_f64();
            },
        )
    }).await;

    //kill the validator
    if validator.id().is_some() {
        validator.kill().await.unwrap(); //should probably be safe because of the above if statements
        validator_time = timelim as f64;
        //eprintln!("terminated validator");
    }

    //kill new_submission
    if new_submission.id().is_some() {
        new_submission.kill().await.unwrap();
        new_submission_time = timelim as f64;
        new_submission_status = SIGUSR1;
    }
    
    //kill old_submission
    if old_submission.id().is_some() {
        old_submission.kill().await.unwrap();
        old_submission_time = timelim as f64;
        old_submission_status = SIGUSR1;
    }
    
    //assume draw if validator crashed
    if validator_status == -1 {
        validator_status = 43 << 8;
    }
    
    //TODO: add signaling of who exited first
    print!("{} {:.6} {} {:.6} {} {:.6}", 
        validator_status, validator_time,
        new_submission_status, new_submission_time,
        old_submission_status, old_submission_time,
    );
    
    Ok(())
}