#include <signal.h>
#include <stdio.h>
#include <stdlib.h>

/* Based on the libc manual*/   

/* This flag controls termination of the main loop. */
volatile sig_atomic_t keep_going = 1;
     
/* The signal handler just clears the flag and re-enables itself. */
void catch_alarm (int sig)
{
  keep_going = 0;
  signal (sig, catch_alarm);
}

void do_nothing (void)
{
  int i=0;
  for (i=0;i<1000;i+=1);
}

int main (void)
{
  /* Establish a handler for SIGALRM signals. */
  signal (SIGALRM, catch_alarm);
  /* Set an alarm to go off in a little while. */
  alarm (1);
  /* Check the flag once in a while to see when to quit. */
  while (keep_going)
    do_nothing();
  
  printf("Hello World!\n");
  return EXIT_SUCCESS;
}
