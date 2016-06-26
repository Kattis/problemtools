#!/usr/bin/ruby

STDIN.each_line do |line|
    nums = line.scan(/\d+/).map(&:to_i)
    a = nums[0]
    b = nums[1]
    res = (a - b).abs
    puts res
end
