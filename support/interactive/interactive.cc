#include <cerrno>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <csignal>
#include <cassert>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/time.h>
#include <sys/resource.h>
#include <fcntl.h>
#include <unistd.h>

#define NOFD -1

const int EXITCODE_AC = 42;
#ifdef __linux__
const int PIPE_SIZE = 1<<20; // 1 MiB (the default max value for an unprivileged user)
#endif

int report_fd, walltimelimit;

volatile bool validator_first = false;
volatile int val_pid = -1, user_pid = -1;
volatile int user_status = -1, val_status = -1;
volatile static rusage user_ru;
volatile static rusage val_ru;

double runtime(volatile rusage *ru) {
	if(ru == NULL) return 0;

	struct timeval tv;
	tv.tv_sec = ru->ru_utime.tv_sec + ru->ru_stime.tv_sec;
	tv.tv_usec = ru->ru_utime.tv_usec + ru->ru_stime.tv_usec;
	return (double)tv.tv_sec + (double)tv.tv_usec / 1000000.0;
}

void report(int val_status, double val_time, int user_status, double user_time) {
	FILE * fp = fdopen(report_fd, "w");
	fprintf(fp, "%d %.6lf %d %.6lf %s", val_status, val_time, user_status, user_time,
			validator_first ? "validator" : "submission");
	fclose(fp);
}

void walltime_handler(int) {
	// TODO: make this race-free and signal safe. Right now there's a race
	// between wait returning in main and the pid variables being set to -1,
	// and we call non-signal safe functions...
	// This is likely fine for problemtools, but not for real contest systems.
	// The easiest way to fix this would probably be to kill(-1, SIGKILL) in
	// this handler, set some sig_atomic_t variable, and let main() deal with
	// the aftermath.

	int u_stat = user_status, v_stat = val_status;
	double u_time = 0;

	// Check if validator has already quit while we were waiting for submission
	if (val_pid != -1 && wait4(val_pid, &v_stat, WNOHANG, (rusage*)&val_ru) != val_pid)  {
		kill(val_pid, SIGTERM);
	}

	// Check submission resource usage and then kill it
	if (user_pid != -1 && wait4(user_pid, &u_stat, WNOHANG, (rusage*)&user_ru) != user_pid) {
		kill(user_pid, SIGKILL);
	}
	u_time = runtime(&user_ru);

	if (u_stat == -1) {
		u_stat = SIGUSR1;
		u_time = walltimelimit;
	}

	// If validator didn't yet give us something, assume WA
	if (v_stat == -1) v_stat = 43 << 8;

	report(v_stat, runtime(&val_ru), u_stat, u_time);
	exit(0);
}

/** Sets the FD_CLOEXEC flag on file descriptor fd to cloexec
 *
 * N.B. Will exit() on failure
 */
void set_cloexec(int fd, int cloexec) {
	int flags;

	flags = fcntl(fd, F_GETFD, 0);
	if(flags < 0) {
		perror("fcntl failed");
		exit(EXIT_FAILURE);
	}
	if(cloexec) {
		flags |= FD_CLOEXEC;
	} else {
		flags &= ~FD_CLOEXEC;
	}

	if(fcntl(fd, F_SETFD, flags) == -1) {
		perror("fcntl failed");
		exit(EXIT_FAILURE);
	}
}

/* execute returns PID of child process
 *
 * Forks and has the child execute args[0] with args as argument vector (so it
 * must follow the format for execvp, i.e. be NULL-terminated - you can use
 * args.c to handle it). The child process will have fd[0] for STDIN and fd[1]
 * for STDOUT. If the child should be left with default STDIN/STDOUT, set fd[0]
 * or fd[1] respectivly to NOFD.
 *
 * Will ulimit core to 0, will ulimit CPU time to cputime, or leave it
 * untouched if negative.
 *
 * NB: Will exit() on failure.
 */
int execute(char **args, int fdin, int fdout) {
	int pid;

	pid = fork();
	if(pid == 0) {
		if(fdin != NOFD) {
			/*
			 * In the unlikely event that fd[1] is STDIN, we have to move it
			 * before we copy fdin to STDIN.
			 */
			if(fdout == STDIN_FILENO) {
				int temp;
				temp = dup(fdout);
				if(temp < 0) {
					perror("dup failed");
					exit(EXIT_FAILURE);
				}
				fdout = temp;
				/* Don't need to close, will be over-dup2:ed */
			}

			if(fdin != STDIN_FILENO) {
				if(dup2(fdin, STDIN_FILENO) != STDIN_FILENO) {
					perror("dup2 failed");
					exit(EXIT_FAILURE);
				}
				if(close(fdin)) {
					perror("close failed");
					exit(EXIT_FAILURE);
				}
			}

			set_cloexec(STDIN_FILENO, 0);
		}

		if(fdout != NOFD) {
			if(fdout != STDOUT_FILENO) {
				if(dup2(fdout, STDOUT_FILENO) != STDOUT_FILENO) {
					perror("dup2 failed");
					exit(EXIT_FAILURE);
				}
				if(close(fdout)) {
					perror("close failed");
					exit(EXIT_FAILURE);
				}
			}

			set_cloexec(STDOUT_FILENO, 0);
		}

		if(execvp(args[0], args) == -1) {
			perror("execvp failed");
			exit(EXIT_FAILURE);
		}
	} else if(pid < 0) {
		perror("fork failed");
		exit(EXIT_FAILURE);
	} else {
		return pid;
	}

	/* Unreachable */
	assert(!"Unreachable code");
	return 0;
}

/* makepipe
 *
 * Creates a pipe and assigns the filedescriptors to fd[0] and fd[1].
 * Sets close-on-exec on both ends of the pipe, and attempts to adjust
 * the size of the pipes to the PIPE_SIZE constant defined at the top
 * of this file.
 *
 * NB: will exit() on failure to create the pipe.  (But will ignore
 * failure to set the pipe size and just print a warning on stderr
 * about it.)
 */

void makepipe(int fd[2]) {
#ifdef __linux__
	if(pipe2(fd, O_CLOEXEC)) {
		perror("pipe failed");
		exit(EXIT_FAILURE);
	}

	if (fcntl(fd[0], F_SETPIPE_SZ, PIPE_SIZE) == -1) {
		perror("failed to set pipe size");
	}
#else
	if(pipe(fd)) {
		perror("pipe failed");
		exit(EXIT_FAILURE);
	}
	for(int i = 0; i < 2; i++) {
		set_cloexec(fd[i], 1);
	}
#endif
}


int main(int argc, char **argv) {
	if(argc < 2 || sscanf(argv[1], "%d", &report_fd) != 1 || report_fd < 0) {
		fprintf(stderr, "Bad first argument, expected file descriptor\n");
		exit(EXIT_FAILURE);
	}
	if(argc < 3 || sscanf(argv[2], "%d", &walltimelimit) != 1 || walltimelimit < 0) {
		fprintf(stderr, "Bad second argument, expected wall time limit (0 to disable)\n");
		exit(EXIT_FAILURE);
	}

	char **val_argv = new char*[argc], **user_argv = new char*[argc];
	int val_argc = 0, user_argc = 0;
	for(int i = 3; i < argc && strcmp(argv[i], ";") != 0; ++i)
		val_argv[val_argc++] = argv[i];
	val_argv[val_argc] = NULL;

	for(int i = 3 + val_argc + 1; i < argc; ++i) {
		user_argv[user_argc++] = argv[i];
	}
	user_argv[user_argc] = NULL;

	if(val_argc == 0 || user_argc == 0) {
		fprintf(stderr, "Empty validator or user argument list\n");
		exit(EXIT_FAILURE);
	}

	int fromval[2], fromuser[2];
	makepipe(fromval);
	makepipe(fromuser);

	set_cloexec(report_fd, 1);

	val_pid = execute(val_argv, fromuser[0], fromval[1]);
	user_pid = execute(user_argv, fromval[0], fromuser[1]);
	if(walltimelimit) {
		signal(SIGALRM, walltime_handler);
		alarm(walltimelimit);
	}

	/*
	 * Here we would normally close the pipes we have opened and passed to
	 * the child processes, since we will not be reading from/writing to them.
	 * However, the story is more complicated than that.
	 *
	 * We intentionally wait with closing the write ends of the fromuser/
	 * fromval pipes until the process that owns them stops, to be more sure
	 * about which process terminates first. If we don't, and process A exits
	 * while process B is (erroneously) trying to read, process B might read
	 * EOF and crash/terminate almost simultaneously as A, and wait(2) might
	 * then return process B's PID instead of A's.
	 *
	 * (We do eventually want B to EOF/crash/terminate rather than waiting
	 * for the wall-time limit, just to finish things earlier, we just don't
	 * want it race with the other process. This holds doubly if B is the
	 * validator, which is expected to deal nicely with EOFs. Unfortunately,
	 * we can't just kill B, because it might run with higher privileges than
	 * us -- this happens with isolate.)
	 *
	 * For the read end of the user -> validator channel the story is similar.
	 * If we close it immediately, it means that if the validator decides to
	 * exit with AC (so that we use the submission's verdict), it's a race
	 * whether a submission that writes during validator exit will get SIGPIPE
	 * or not. Thus, we must wait until the validator has exited with non-AC
	 * to close this pipe end, or we will get unpredictable verdicts.
	 *
	 * (This can also be worked around on the validator side, by making sure to
	 * read EOF before exiting with AC. Not all validators do that, however.)
	 *
	 * We never close the read end of the validator -> user channel -- it only
	 * serves to give the validator Judge Error if it doesn't setup up a signal
	 * handler for SIGPIPE, and we do want submissions that exit early to be
	 * accepted.
	 */

	int remaining = 2;
	while (remaining > 0) {
		int status;
		struct rusage ru;
		int r = wait3(&status, 0, &ru);
		if (r == -1) {
			perror("wait failed");
			exit(1);
		}
		if (r == val_pid) {
			if (remaining == 2) {
				validator_first = true;
				if (!(WIFEXITED(status) && WEXITSTATUS(status) == EXITCODE_AC)) {
					// See comment above.
					close(fromuser[0]);
				}
			}
			val_status = status;
			memcpy((void*)&val_ru, &ru, sizeof(rusage));
			val_pid = -1;
			remaining--;
			close(fromval[1]);
		}
		if (r == user_pid) {
			user_status = status;
			memcpy((void*)&user_ru, &ru, sizeof(rusage));
			user_pid = -1;
			remaining--;
			close(fromuser[1]);
		}
	}

	report(val_status, runtime(&val_ru), user_status, runtime(&user_ru));
	return 0;
}
