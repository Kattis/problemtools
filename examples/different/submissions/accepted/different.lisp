(loop for a = (read *standard-input* nil) until (null a) do
      (let ((b (read)))
        (format t "~a~%" (abs (- a b)))))
