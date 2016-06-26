var line;

while (line = readline()) {
    var nums = line.split(' ');
    var a = parseInt(nums[0]);
    var b = parseInt(nums[1]);
    var res = Math.abs(a - b);
    print(res);
}
