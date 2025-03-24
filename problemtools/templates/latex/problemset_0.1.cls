\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{problemset}[2011/08/26 Problem Set For ACM-Style Programming Contests]


% Options to add:
% noproblemnumbers
% nosamplenumbers
% nopagenumbers
% nofooter
% noheader

\newif\ifplastex
\plastexfalse

\newif\if@footer\@footertrue
\DeclareOption{nofooter}{\@footerfalse}

\newif\if@problemnumbers\@problemnumberstrue
\DeclareOption{noproblemnumbers}{\@problemnumbersfalse}

\newif\if@clearevenpages\@clearevenpagestrue

\DeclareOption{plainproblems}{
  \@footerfalse
  \@problemnumbersfalse
  \@clearevenpagesfalse
}

%\DeclareOption{noproblemnumbers}{...}

\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
\ProcessOptions\relax

\LoadClass{article}

\RequirePackage{times}            % Font choice
\RequirePackage{amsmath}          % AMS
\RequirePackage{amssymb}          % AMS
\RequirePackage[OT2,T1]{fontenc}  % Cyrillic and standard % TODO: make alphabet options more general
\RequirePackage[utf8]{inputenc}   % UTF-8 support
\RequirePackage{fancyhdr}         % Headers
\RequirePackage{graphicx}         % Graphics
\RequirePackage{subfigure}        % Subfigures
\RequirePackage{wrapfig}          % Illustrations
\RequirePackage{import}           % Proper file inclusion
\RequirePackage{verbatim}         % For samples
\RequirePackage{fullpage}         % Set up margins for full page
\RequirePackage{url}              % Urls
\RequirePackage[colorlinks=true]{hyperref}
\RequirePackage{ulem}             % \sout


%% Commands used to set name, logo, etc of contest
\newcommand*{\contestname}[1]{\def\@contestname{#1}}
\newcommand*{\contestshortname}[1]{\def\@contestshortname{#1}}
\newcommand*{\contestlogo}[1]{\def\@contestlogo{#1}}
\newcommand*{\headerlogo}[1]{\def\@headerlogo{#1}}
\newcommand*{\location}[1]{\def\@location{#1}}
\newcommand*{\licenseblurb}[1]{\def\@licenseblurb{#1}}
\newcommand*{\problemlanguage}[1]{\def\@problemlanguage{#1}}
\contestname{}
\contestshortname{}
\contestlogo{}
\headerlogo{}
\location{}
\licenseblurb{}
\problemlanguage{}



% Typesetting sections in a problem

\renewcommand\section{\@startsection{section}{1}{\z@}%
                                   {-3.5ex \@plus -1ex \@minus -.2ex}%
                                   {2.3ex \@plus.2ex}%
                                   {\normalfont\large\sf\bfseries}}

\renewcommand\subsection{\@startsection{subsection}{2}{\z@}%
                                     {-3.25ex\@plus -1ex \@minus -.2ex}%
                                     {1.5ex \@plus .2ex}%
                                     {\normalfont\normalsize\sf\bfseries}}

\renewcommand{\contentsname}{Problems}


% TODO: make last command of illustration/figure optional

\newcommand{\illustration}[3]{
  \begin{wrapfigure}{r}{#1\textwidth}
    \includegraphics[width=#1\textwidth]{#2}
    \begin{flushright}
      \vspace{-9pt}
      \tiny #3
    \end{flushright}
    \vspace{-15pt}
  \end{wrapfigure}
  \par
  \noindent
}


%% Redefine cleardoublepage to put a text on even-numbered empty
%% pages.
\newcommand{\makeemptypage}{
  ~\thispagestyle{empty} 
  \vfill
  \centerline{\Large \textsf{ This page is intentionally left (almost) blank.}}
  \vfill
  \clearpage
}
\renewcommand{\cleardoublepage}{
  \clearpage%
  \ifodd\value{page}\else\makeemptypage\fi%
}

\newcommand{\clearproblemsetpage}{
  \if@clearevenpages
  \cleardoublepage
  \else
  \clearpage
  \fi
}


%% Set up a problem counter and number problems A B C ...
\newcounter{problemcount}
\setcounter{problemcount}{0}
\newcommand{\problemnumber}{\Alph{problemcount}}

%% Number figures as A.1 A.2... B.1 B.2... (except if we're converting to HTML)
\ifplastex\else
\renewcommand{\thefigure}{\problemnumber.\arabic{figure}}
\fi


%% Command for starting new problem

%% Problem inclusion
\newcommand{\includeproblem}[3]{
  \startproblem{#1}{#2}{#3}
  \import{#1/problem_statement/}{problem\@problemlanguage.tex}
}

\newcommand{\startproblem}[3]{
  \clearproblemsetpage
  \refstepcounter{problemcount}
  \setcounter{samplenum}{0}
  \setcounter{figure}{0}%
  \def\@problemid{#1}
  \def\@problemname{#2}
  \def\@timelimit{#3}
  \problemheader{\@problemname}{\@problemid}
}

\newcommand{\problemheader}[2]{
  \begin{center}
    \textsf{
      {\huge #1\\}
      {\Large Problem ID: #2\\}
    }
  \end{center}
}

%% Commands related to sample data

%% Sample counter
\newcounter{samplenum}
\newcommand{\sampleid}{\arabic{samplenum}}

%% Define the command used to give sample data
%% Takes filename as parameter

\newcommand{\includesample}[1]{
  \displaysample{\@problemid/data/sample/#1}
}

\newcommand{\displaysample}[1]{
  \IfFileExists{#1.in}{}{\ClassError{problemset}{Can't find file '#1.in'}{}}
  \IfFileExists{#1.ans}{}{\ClassError{problemset}{Can't find file '#1.ans'}{}}
  \refstepcounter{samplenum}
  \par
  \vspace{0.4cm}
  \noindent
  \sampletable
      {Sample Input \sampleid}{#1.in}
      {Sample Output \sampleid}{#1.ans}
}

\newcommand{\sampletable}[4]{
  \begin{tabular}{|l|l|}
    \multicolumn{1}{l}{\textsf{\textbf{#1}}} &
    \multicolumn{1}{l}{\textsf{\textbf{#3}}} \\
    \hline
    \parbox[t]{0.475\textwidth}{\vspace{-0.5cm}\verbatiminput{#2}}
    &
    \parbox[t]{0.475\textwidth}{\vspace{-0.5cm}\verbatiminput{#4}}
    \\
    \hline
  \end{tabular}
}


% Remaining part of file is headers and toc, not tested with plasTeX
% and should not be used in plastex mode
\ifplastex\else


%% Set up headers
\fancypagestyle{problem}{
  \fancyhf{} % Clear old junk
%  \ifx \@headerlogo \@empty\relax \else
%  \fancyhead[C]{
%    \includegraphics[scale=0.3]{\@headerlogo}
%  }
%  \fi
  \if@footer
  \fancyhead[L]{
    \emph{
      \@contestshortname{}
      \if@problemnumbers Problem \problemnumber:{} \fi
      \@problemname
    }
  }
  \fancyhead[R]{\thepage}
  \fancyfoot[L]{
    \emph{\@licenseblurb}
  }
%  \fancyfoot[R]{\includegraphics[scale=0.5]{cc-by-sa} }
  \fi
}
\renewcommand{\headrulewidth}{0pt}
\pagestyle{problem}

\AtBeginDocument{
  % FIXME: Figure out how to do this in a header-indep. way.
%  \ifx \@headerlogo \@empty \relax\else
  \addtolength{\headheight}{12pt}
  \addtolength{\topmargin}{-30pt}
  \addtolength{\textheight}{18pt}
%  \fi
  \setlength{\headsep}{25pt} 
}


% Set up table of contents for cover page
\AtBeginDocument{
  \addtocontents{toc}{\protect\begin{tabular}{cl}}
}
\AtEndDocument{
  \clearproblemsetpage
  % Annoyingly enough addtocontents won't work at end of doc
  \immediate\write\@auxout{%
    \string\@writefile{toc}{\string\end{tabular}}%
  }
}

\fi
